import os
from uuid import uuid4 as uuid
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup

load_dotenv()

LIBGEN_URL = 'https://libgen.is/search.php'
client = httpx.Client(base_url=LIBGEN_URL)

TOKEN = os.getenv('TOKEN')
WELCOME_MESSAGE = '''Welcome to Book Downloader Bot. 

Any time send me the book name you want to download.

created by @chapimenge

'''

BOOK_TEXT_TEMPLATE = '''Author: {author}
Title: {title}
Size: {size}
Type: {file}
Year: {year}
'''


def send_request(url, url_params=None):
    res = client.get(url, params=url_params)

    return res.text


def get_file_url(mirror):
    page = send_request(mirror)
    soup = BeautifulSoup(page, features='html.parser')
    a = soup.find('a')
    h1 = soup.find('h1')
    url = a.get('href') if a else None
    file_name = h1.get_text() if h1 else None
    return url, file_name


def download_book(url, file_name, timeout=20, query=None):
    query.edit_message_text(f'Downloading {file_name[:10]}...')
    with open(file_name, 'wb') as f:
        with httpx.stream("GET", url, timeout=timeout) as response:
            total = int(response.headers["Content-Length"])
            num_bytes_downloaded = response.num_bytes_downloaded
            prev = 0
            for chunk in response.iter_bytes():
                f.write(chunk)
                percent = (response.num_bytes_downloaded / total) * 100
                tmp = (percent//10) * 5
                if percent and tmp != prev:
                    query.edit_message_text(
                        f'Downloading... {tmp:.2f}%')
                prev = tmp

    query.edit_message_text('Downloading completed!')


def get_books(html):
    books = []
    soup = BeautifulSoup(html, features='html.parser')
    # search for table tag with class 'c'
    table = soup.find('table', class_='c')
    rows = table.find_all('tr')
    for i, row in enumerate(rows):
        if len(books) == 10:
            break
        if i != 0:
            tds = row.find_all('td')
            book = {}
            for j, td in enumerate(tds):
                if j == 0 or j == 5:
                    continue
                elif j == 1:
                    book['author'] = td.get_text()
                elif j == 2:
                    book['title'] = td.find('a').get_text()
                elif j == 3:
                    book['publisher'] = td.get_text()
                elif j == 4:
                    book['year'] = td.get_text()
                elif j == 6:
                    book['language'] = td.get_text()
                elif j == 7:
                    book['size'] = td.get_text()
                elif j == 8:
                    book['file'] = td.get_text()
                else:
                    text = td.find('a').get_text()
                    link = td.find('a').get('href')
                    if text.lower() == '[edit]':
                        continue
                    if 'link' not in book:
                        book['link'] = link

            if 'mb' in book['size'].lower():
                size = float(book['size'].split()[0])
                if size > 50:
                    continue
            if book and book not in books:
                books.append(book)

    return books[:10]


def search_book(name):
    url_params = {
        'req': name,
        'res': 25,
        'view': 'simple',
        'column': 'def',
        'phrase': 1,
        'sort': 'year',
        'sortmode': 'DESC',
        'open': 0
    }

    response = send_request(LIBGEN_URL, url_params)
    books = get_books(response)
    return books


def start(update, context):
    update.message.reply_text(WELCOME_MESSAGE)


def search_book_handler(update, context):
    update.message.reply_text(
        'For better results, please enter the name of the book')
    update.message.reply_text('Searching...')
    text = update.message.text
    books = search_book(text)
    if not books:
        update.message.reply_text('No books found!')
        return 1
    response_text = 'Books that are greater than 50 MB wont be listed here.\n\nHere are the top 10 books I found for you\n\n'
    keyboards = []
    row = []
    for i, book in enumerate(books):
        response_text += f'{i+1}. '
        response_text += BOOK_TEXT_TEMPLATE.format(**book)
        response_text += '\n'

        row.append(InlineKeyboardButton(
            str(i+1), callback_data=f'link_{book["link"]}'))
        if len(row) == 2:
            keyboards.append(row)
            row = []
    if row:
        keyboards.append(row)

    update.message.reply_text(
        response_text, reply_markup=InlineKeyboardMarkup(keyboards))
    return 1


def send_file(update, context):
    query = update.callback_query
    link = query.data.split('_')[1]
    query.answer()
    query.edit_message_text(text='getting the file...')
    url, file_name = get_file_url(link)
    unique = str(uuid())[:8]
    unique_file_name = '-'.join(file_name.lower().split())
    file_type = url.split('.')[-1]
    unique_file_name = f'{unique_file_name}-{unique}.{file_type}'
    download_book(url, unique_file_name, query=query)
    query.edit_message_text(text='sending the file...')
    context.bot.send_chat_action(
        chat_id=query.message.chat_id, action=ChatAction.UPLOAD_DOCUMENT)
    
    context.bot.send_document(
        chat_id=query.message.chat_id,
        document=open(unique_file_name, 'rb'),
        filename=file_name
    )
    try:
        os.remove(unique_file_name)
    except:
        pass
    return 1


def main():
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(MessageHandler(Filters.text, search_book_handler))
    dispatcher.add_handler(CallbackQueryHandler(send_file))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
