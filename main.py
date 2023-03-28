import os
import time
import telebot
import secrets
import threading, schedule
import string
import qrcode
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv import load_dotenv
from airtable_api import *
from io import BytesIO
from configparser import ConfigParser

load_dotenv()
TOKEN = os.getenv('TOKEN')

# Initialize the bot with your token
bot = telebot.TeleBot(TOKEN, parse_mode='MARKDOWN', num_threads=10)

directory = os.path.dirname(os.path.realpath(__file__))
config = ConfigParser()
config.read(f'{directory}/config.ini')

mentor_passcodes = {'python':'',
                    'web':'',
                    'mobile':'',
                    'blockchain':'',
                    'ai':'',
                    'resume':'',
                    'iot':'',
                    'pcb':'',
                    '3d':'',
                    'gdsc':''}

for station_name in mentor_passcodes:
    mentor_passcodes[station_name] = str(config.get('bot', station_name))

visitor_codes = {}
last_seen_chat_id = {}
last_seen_message = {}
last_mentor_request = {}

def randomise_visitor_codes():
    global visitor_codes
    for key in mentor_passcodes.keys():
        new_code = ''.join(secrets.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(6))
        visitor_codes[key] = new_code
    global start_time
    print(visitor_codes)
    start_time = time.time()
        
schedule.every(120).seconds.do(randomise_visitor_codes)

def validate_visitor_codes(code):
    global visitor_codes
    if code in visitor_codes.values():
        for key in visitor_codes.keys():
            if visitor_codes[key] == code:
                station_name = key
        return station_name
    else:
        return False
    
def deserialize_list(list):
    if list != '[]':
        list = list.strip('][').split(', ')
        list = [x.strip("'") for x in list]
    else: list = []
    return list

def progress_as_text(visited_list):
    if len(visited_list) < 1:
        text = "You haven't visited any stations yet 🚫"
        return text
    else:
        text = "*Stations visited*\n\n"
        for station_name in visitor_codes.keys():
            status = station_name.capitalize()
            if station_name in visited_list:
                status += " ✅"
            text = text + status + "\n"
        return text
    
def generate_qr(code):
    qr_obj = qrcode.QRCode(version=1, box_size=10, border=2)
    qr_obj.add_data(code)
    qr_obj.make(fit=True)
    qr_img = qr_obj.make_image(fill_color='black', back_color='white')
    out = BytesIO()
    qr_img.save(out, format='PNG')
    return out

# Handler for the "/start" command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        participant_data = get_participant_data(message.from_user.id)['fields']
        visited_list = deserialize_list(participant_data['visited'])
        if participant_data['type'] in mentor_passcodes:
            bot.send_message(message.chat.id, f'''You have already completed registration as a *Mentor* 🧑‍🏫

*Here are your details:*
_Name: {participant_data['name']}_
_Station name: {participant_data['type'].capitalize()}_

If you want to move to a different station, you can run /cleardata command to clear your current data from the database.''')
        elif participant_data['type'] == 'learner':
            bot.send_message(message.chat.id, f'''You have already completed registration as a *Learner* 🧑‍🎓

*Here are your details:*
_Name: {participant_data['name']}_
_Email: {participant_data['email']}_
_No. of stations visited: {len(visited_list)}_

If you wish to change any of your details, you can run /cleardata _(clears all your current data including your progress from our database)_ and then rerun the /start command''')
    except:
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Mentor', callback_data='mentor'),
                InlineKeyboardButton('Learner', callback_data='learner'))
        msg = bot.send_message(message.chat.id, "Welcome to Learing Stations @ Dyuksha '23 hosted TinkerHub NSSCE! I'm BB8 you're learning assistant. So are you a mentor or a learner?", reply_markup=markup)

@bot.message_handler(commands=['visited'])
def visited_station(message):
    args = message.text.split()
    if len(args) == 2:
        code = args[1]
        if validate_visitor_codes(code):
            station_name = validate_visitor_codes(code)
            try:
                record_id = get_record_id(message.from_user.id)
                learner_data = get_participant_data(message.from_user.id)['fields']
                visited_list = deserialize_list(learner_data['visited'])
                if learner_data['type'] == 'learner':
                    if station_name not in visited_list:
                        visited_list.append(station_name)
                        update_visited(str(visited_list), record_id)
                        if len(visited_list) < 10:
                            bot.send_message(message.chat.id, f"Yaay! you've succesfully visited the {station_name} station 🥁. {10 - len(visited_list)} stations left..")
                        else:
                            bot.send_message(message.chat.id, f"Yaay! you've succesfully visited the {station_name} station 🥁.")
                            bot.send_message(message.chat.id, f"Congratulations, you've visited all our stations 🎉. Here's a token of appreciation for your efforts!")
                    else:
                        bot.send_message(message.chat.id, f"You've already visited the {station_name} station 👀. Please visit a different station.")
                else:
                    bot.send_message(message.chat.id, "You need to be a *Learner* 🎓 to run this command!")
            except Exception as e:
                bot.send_message(message.chat.id, "You need to register as a *Learner* 🎓 to run this command. Use the /start command to register first.")
        else:
            bot.send_message(message.chat.id, "Invalid visitor code ❌ Please ask your mentor for a valid one!")
    else:
        bot.send_message(message.chat.id, "Usage: /visited <VISTOR CODE>. Ask your mentor for the visitor code!")

@bot.message_handler(commands=['cleardata'])
def clear_participant_data(message):
    tu_id = message.from_user.id
    try:
        participant_data = get_participant_data(tu_id)['fields']
        if participant_data['type'] in mentor_passcodes:
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton('Yes', callback_data='yes'),
                        InlineKeyboardButton('No', callback_data='no'))
            bot.send_message(message.chat.id, "Are you sure you want to clear your current data from the database ⚠?", reply_markup=markup)
        elif participant_data['type'] == 'learner':
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton('Yes', callback_data='yes'),
                        InlineKeyboardButton('No', callback_data='no'))
            bot.send_message(message.chat.id, "Are you sure you want to clear all your current data from the database? This will *also reset your progress* ⚠", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, "You need to be a *Mentor* or *Learner* to run this command! Use the /start command to register first")

@bot.message_handler(commands=['checkprogress'])
def check_progress(message):
    tu_id = message.from_user.id
    try:
        participant_data = get_participant_data(tu_id)['fields']
        visited_list = deserialize_list(participant_data['visited'])
        if participant_data['type'] == 'learner':
            text = progress_as_text(visited_list)
            bot.send_message(message.chat.id, text=text)
        else:
            bot.send_message(message.chat.id, "You need to register as a *Learner* 🎓 to run this command! Use the /start command to register first")
    except Exception as e:
        bot.send_message(message.chat.id, "You need to register as a *Learner* 🎓 to run this command! Use the /start command to register first")

def process_passcode(message):
    # Code to check the passcode and proceed accordingly
    global last_seen_message, last_seen_chat_id
    passcode = message.text
    if passcode in mentor_passcodes.values():
        bot.delete_message(message.chat.id, message.message_id)
        mentor_name = message.from_user.first_name
        mentor_tu_id = message.from_user.id
        for key in mentor_passcodes.keys():
            if mentor_passcodes[key] == passcode:
                station_name = key
        add_new_record(mentor_name, station_name, str(mentor_tu_id))
        code = visitor_codes[station_name]
        qr_img = generate_qr(code)
        qr_img.seek(0)
        time_left = time.time() - start_time
        minutes_left = f"{int(1 - time_left//60)}"
        seconds_left = f"{int(60 - time_left%60)}"
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Refresh Code', callback_data='refresh'))
        bot.send_photo(message.chat.id, qr_img, caption=f"Hey there {station_name} mentor. Here's the visitor code for your station: *{code}* - the visitors may either type this code manually or scan the above qr to copy the code. This code expires in *{minutes_left}:{seconds_left}* minutes", reply_markup=markup)
        if message.from_user.id in last_mentor_request:
            last_mentor_request.pop(message.from_user.id)
        if message.from_user.id in last_seen_chat_id:
            bot.delete_message(last_seen_chat_id[message.from_user.id], last_seen_message[message.from_user.id])
            last_seen_message.pop(message.from_user.id)
            last_seen_chat_id.pop(message.from_user.id)
    else:
        bot.send_message(message.chat.id, "Invalid passcode ❌, please try again. If you are not a *Mentor*, run /start again and select *Learner* option.")
        if message.from_user.id in last_mentor_request:
            bot.delete_message(last_mentor_request[message.from_user.id][0], last_mentor_request[message.from_user.id][1])
            last_mentor_request.pop(message.from_user.id)

def process_name(message):
    name = message.text
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton('Go back', callback_data='back'))
    msg = bot.send_message(message.chat.id, "Hi " + name + "! Please enter your email:")
    bot.register_next_step_handler(msg, process_email, name)

def process_email(message, name):
    global last_seen_message, last_seen_chat_id
    name = name
    type = 'learner'
    email = message.text
    learner_tu_id = str(message.from_user.id)
    add_new_record(name, type, learner_tu_id, email)
    bot.send_message(message.chat.id, "Awesome! Now you're all set to start learning. Which station are you gonna visit first?")
    if message.from_user.id in last_seen_chat_id:
        bot.delete_message(last_seen_chat_id[message.from_user.id], last_seen_message[message.from_user.id])
        last_seen_message.pop(message.from_user.id)
        last_seen_chat_id.pop(message.from_user.id)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global last_seen_chat_id, last_seen_chat_id, last_mentor_request
    if call.data == 'mentor':
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Go back', callback_data='back'))
        msg = bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='Please enter the passcode:', reply_markup=markup)
        last_seen_chat_id[call.from_user.id] = call.message.chat.id
        last_seen_message[call.from_user.id] = call.message.message_id
        last_mentor_request[call.from_user.id] = [call.message.chat.id, call.message.message_id]
        bot.register_next_step_handler(msg, process_passcode)
    elif call.data == 'learner':
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Go back', callback_data='back'))
        msg = bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='Please enter your name:', reply_markup=markup)
        last_seen_chat_id[call.from_user.id] = call.message.chat.id
        last_seen_message[call.from_user.id] = call.message.message_id
        bot.register_next_step_handler(msg, process_name)
    elif call.data == 'back':
        if call.from_user.id in last_seen_chat_id:
            bot.clear_step_handler_by_chat_id(call.message.chat.id)
            last_seen_chat_id.pop(call.from_user.id)
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Mentor', callback_data='mentor'),
                   InlineKeyboardButton('Learner', callback_data='learner'))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Welcome to Learing Stations @ Dyuksha '23 hosted TinkerHub NSSCE! I'm BB8 you're learning assistant. So are you a mentor or a learner?", reply_markup=markup)
    elif call.data == 'refresh':
        mentor_tu_id = str(call.from_user.id)
        mentor_data = get_participant_data(mentor_tu_id)['fields']
        station_name = mentor_data['type']
        code = visitor_codes[station_name]
        qr_img = generate_qr(code)
        qr_img.seek(0)
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Refresh Code', callback_data='refresh'))
        time_left = time.time() - start_time
        minutes_left = f"{int(1 - time_left//60)}"
        seconds_left = f"{int(60 - time_left%60)}"
        bot.edit_message_media(media=InputMediaPhoto(qr_img, caption=f"Hey there {station_name} mentor. Here's the visitor code for your station: {code} - the visitors may either type this code manually or scan the above qr to copy the code. This code expires in {minutes_left}:{seconds_left} minutes"), chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        msg = bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=f"Hey there {station_name} mentor. Here's the visitor code for your station: *{code}* - the visitors may either type this code manually or scan the above qr to copy the code. This code expires in *{minutes_left}:{seconds_left}* minutes", reply_markup=markup)
    elif call.data == 'yes':
        try:
            delete_last_record(call.from_user.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "Succesfully deleted all your data 🗑️. Run /start to register again.")
        except:
            bot.delete_message(call.message.chat.id, call.message.message_id)
    elif call.data == 'no':
        bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == '__main__':
    threading.Thread(target=bot.infinity_polling, name='bot_infinity_polling', daemon=True).start()
    randomise_visitor_codes()
    while True:
        schedule.run_pending()
        time.sleep(1)
