import os
import math
import base64
from datetime import datetime
from uuid import uuid4 as uuid
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters, ConversationHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction, Update
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup
from deta import Deta
import json
import traceback
import html
from telegram.utils.helpers import mention_html


load_dotenv()

TOKEN = os.getenv('TOKEN', '1789117801:AAE7kPyd23Xbq3kPSvFH5OHMzAkHY96xJsc')
DETA_KEY = os.getenv(
    'DETA_KEY', 'd0fx3kttcjd_7CrquXya2gHRf448TjjnU1BcAQxnJs83')

ADMIN_ID = [1697562512]

deta = Deta(DETA_KEY)
db = deta.Base('amazingbookdownloaderbot')
if not db.get('total_downloads'):
    db.put({
        'key': 'total_downloads',
        'value': 0
    })

LIBGEN_URL = 'https://libgen.is/search.php'
# other mirros
LIBGEN_MIRRORS = [
    'http://gen.lib.rus.ec/search.php',
    'http://gen.lib.rus.ec/search.php',
    'http://libgen.rs/search.php'
]

client = httpx.Client(base_url=LIBGEN_URL)


WELCOME_MESSAGE = '''Welcome to Book Downloader Bot. 

Any time send me the book name you want to download. 50MB is the maximum size of the book you can download.

created by @chapimenge

Join https://t.me/codewizme for more bots and projects.

'''

BOOK_TEXT_TEMPLATE = '''Author: {author}
Title: {title}
Size: {size}
Type: {file}
Year: {year}
'''


def create_user(user_info):
    user_info['id'] = str(user_info.get('id'))
    existing_user = db.get(user_info['id'])
    if existing_user:
        return
    user_info['key'] = user_info.pop('id')
    db.put(user_info)
    return


def send_request(url, url_params=None):
    res = client.get(url, params=url_params)
    if res.status_code == 200:
        return res.text
    try:
        for mirror in LIBGEN_MIRRORS:
            res = client.get(mirror, params=url_params)
            if res.status_code == 200:
                return res.text
    except:
        pass

    return None


def get_file_url(mirror):
    page = send_request(mirror)
    if not page:
        return None
    soup = BeautifulSoup(page, features='html.parser')
    a = soup.find('a')
    h1 = soup.find('h1')
    url = a.get('href') if a else None
    file_name = h1.get_text() if h1 else None
    return url, file_name


def download_book(url, file_name, timeout=20, query=None):
    query.edit_message_text(f'Downloading {file_name}...')
    total = 0
    # make sure the file extension is set
    with open(file_name, 'wb') as f:
        with httpx.stream("GET", url, timeout=timeout) as response:
            total = int(response.headers["Content-Length"])
            prev = 0
            for chunk in response.iter_bytes():
                f.write(chunk)
                percent = (response.num_bytes_downloaded / total) * 100
                tmp = (percent//10) * 5
                if percent and tmp != prev:
                    try:
                        query.edit_message_text(
                            f'Downloading... {tmp:.2f}%')
                    except Exception as e:
                        print(e)
                prev = tmp

    try:
        query.edit_message_text('Downloading completed!')
    except Exception as e:
        print('Error Downlading', e)

    total_mb = math.ceil(total / 1024 / 1024)
    db.update({
        'value': db.get('total_downloads')['value'] + total_mb
    }, 'total_downloads')


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
    if not response:
        return []
    books = get_books(response)
    return books


def start(update, context):
    # every even day of the month send the user stat of total downloads
    today = datetime.today()
    if today.day % 2 == 0:
        total_downloads = db.get('total_downloads')['value']
        update.message.reply_text(
            f'{WELCOME_MESSAGE} \n\nTotal downloads from all till now: {total_downloads} MB')
    else:
        update.message.reply_text(WELCOME_MESSAGE)

    user_info = update.message.from_user.to_dict()
    create_user(user_info)


def search_book_handler(update, context):
    update.message.reply_text(
        'For better results, please enter the name of the book')
    update.message.reply_text('Searching...')
    text = update.message.text
    books = search_book(text)
    if not books:
        update.message.reply_text('No books found or Error occurred')
        return 1
    response_text = 'Books that are greater than 50 MB wont be listed here.\n\nHere are the top 10 books I found for you\n\n'
    keyboards = []
    row = []
    for i, book in enumerate(books):
        response_text += f'{i+1}. '
        response_text += BOOK_TEXT_TEMPLATE.format(**book)
        response_text += '\n'

        button_data = f'link_{book["link"].split("/")[-1]}&file={book["file"]}'
        row.append(InlineKeyboardButton(
            str(i+1), callback_data=button_data))
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
    data = query.data.split('&')
    link = f'http://library.lol/main/{data[0].split("_")[1]}'
    query.answer()
    query.edit_message_text(text='getting the file...')
    url, file_name = get_file_url(link)
    unique = str(uuid())[:8]
    unique_file_name = '-'.join(file_name.lower().split())
    file_type = data[1].split('=')[1]
    unique_file_name = f'books/{unique_file_name}-{unique}.{file_type}'
    download_book(url, unique_file_name, query=query)
    if file_name.split('.')[-1] != file_type:
        file_name = f'{file_name}.{file_type}'
    try:
        query.edit_message_text(text='sending the file...')
    except:
        update.message.reply_text('sending the file...')

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


def get_stat(update, context):
    if update.message.from_user.id not in ADMIN_ID:
        return 1
    total_downloads = db.get('total_downloads')['value']
    res = db.fetch()
    all_items = res.items
    while res.last:
        res = db.fetch(last=res.last)
        all_items += res.items

    text = 'Total downloads: {:.2f} MB\n\n'.format(total_downloads)
    text += 'Total users: {}\n\n'.format(len(all_items)-1)

    update.message.reply_text(text)


def error_handler(update, context):
    print("Exception while handling an update:")

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f'An exception was raised while handling an update\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}'
        '</pre>\n\n'
        f'<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n'
        f'<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )

    # Finally, send the message
    context.bot.send_message(
        chat_id=1697562512, text=message, parse_mode="HTML")
    update.message.reply_text(
        'Sorry, something went wrong. Please try again later.')


def broadcast_message(update: Update, context):
    if update.effective_user.id not in ADMIN_ID:
        update.message.reply_text('Unrecognized command')
        return ConversationHandler.END
    update.message.reply_text('Enter the message to broadcast')
    return 1


def send_broadcast_message(update, context):
    data = {
        'from_chat_id': update.message.chat_id,
        'message_id': update.message.message_id,
    }
    context.job_queue.run_once(broadcast_job, 0, context=data)
    update.message.reply_text('Broadcasting message...')
    return ConversationHandler.END


def broadcast_job(context):
    print('Broadcast Job started')
    res = db.fetch()
    all_items = res.items
    while res.last:
        res = db.fetch(last=res.last)
        all_items += res.items
    # copy message to the user
    import time
    print('total users: ', len(all_items)-1)
    sent = 0
    for user in all_items:
        if user['key'] == 'total_downloads':
            continue
        try:

            print(user)
            if sent > 0:
                break
            context.bot.copy_message(
                chat_id=int(user['key']),
                **context.job.context,
            )
            sent += 1
        except Exception as e:
            print('Error sending message to ', user)
            print('Error is ', e)
        time.sleep(0.3)
    print('Broadcast Job finished')
    # send message to the admin
    context.bot.send_message(
        chat_id=1697562512,
        text=f'Broadcast Job finished. Sent to {sent} users from {len(all_items)-1} users',
    )

    context.job.schedule_removal()


def cancel(update, context):
    update.message.reply_text('Cancelled')
    return ConversationHandler.END


def clean_files(context):
    print('Cleaning files')
    now = datetime.now()
    # list all files in the books folder
    for file in os.listdir('books'):
        last_modified = os.path.getmtime(os.path.join('books', file))
        last_modified = datetime.fromtimestamp(last_modified)
        total_seconds = (now - last_modified).total_seconds()
        # if the file is older than an hour, delete it
        if total_seconds > 3600:
            os.remove(os.path.join('books', file))

    return


broadcast_conv = ConversationHandler(
    entry_points=[CommandHandler('broadcast', broadcast_message)],
    states={
        1: [MessageHandler(Filters.all, send_broadcast_message)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)


def main():
    updater = Updater(token=TOKEN, use_context=True, workers=32)
    dispatcher = updater.dispatcher
    job = updater.job_queue
    
    # run the clean_files function every hour
    job.run_repeating(clean_files, interval=3600, first=10)

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('stat', get_stat))
    dispatcher.add_handler(broadcast_conv)
    dispatcher.add_handler(MessageHandler(
        Filters.text, search_book_handler, run_async=True))
    dispatcher.add_handler(CallbackQueryHandler(send_file, run_async=True))
    dispatcher.add_error_handler(error_handler, run_async=True)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
