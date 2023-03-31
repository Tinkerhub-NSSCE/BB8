import os
import time
import telebot
import secrets
import threading, schedule
import string
import qrcode
import json
import logging
import pytz
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv import load_dotenv
from airtable_api import *
from io import BytesIO
from configparser import ConfigParser
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

load_dotenv()
TOKEN = os.getenv('TOKEN')

directory = os.path.dirname(os.path.realpath(__file__))
config = ConfigParser()
config.read(f'{directory}/config.ini')

num_threads = int(config.get('bot','num_threads'))
randomise_interval = int(config.get('bot','randomise_interval'))
admin_list = json.loads(config.get('bot','admin_list'))
station_names = json.loads(config.get('stations','station_names'))

# initialize the bot
bot = telebot.TeleBot(TOKEN, parse_mode='MARKDOWN', num_threads=num_threads)

# setup logging
log_format = logging.Formatter('%(asctime)s %(levelname)s   %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

bb8_stream_handler = logging.StreamHandler()
bb8_stream_handler.setFormatter(log_format)
bb8_logger = logging.getLogger(__name__)
bb8_logger.addHandler(bb8_stream_handler)
bb8_logger.setLevel(logging.INFO)

local_tz = pytz.timezone('Asia/Calcutta')

def loggable_dt(dt:datetime):
  local_dt = dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
  format_string = "%d-%m-%Y | %I:%M:%S %p"
  lg_dt = local_dt.strftime(format_string)
  return lg_dt

# GLOBAL DICTS

mentor_passcodes = {}
for station_name in station_names:
    mentor_passcodes[station_name] = str(config.get('stations', station_name))
visitor_codes = {}
last_seen_chat_id = {}
last_seen_message = {}
last_mentor_request = {}

# HELPER FUNCTIONS

def randomise_visitor_codes():
    global visitor_codes
    for key in mentor_passcodes.keys():
        new_code = ''.join(secrets.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(6))
        visitor_codes[key] = new_code
    global start_time
    bb8_logger.info(f"New visitor codes generated at {loggable_dt(datetime.utcnow())}")
    start_time = time.time()
        
schedule.every(randomise_interval).seconds.do(randomise_visitor_codes)

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

def progress_as_text(visited_list, participant_data):
    if len(visited_list) < 1:
        text = f'''_Name: {participant_data['name']}_
_Email: {participant_data['email']}_
_Participant ID: {participant_data['primary_key']}_

*Stations visited:*
-------------------------
_You haven't visited any stations yet 🚫_'''
        return text
    else:
        text = f'''_Name: {participant_data['name']}_
_Email: {participant_data['email']}_
_Participant ID: {participant_data['primary_key']}_

*Stations visited:*
-------------------------
'''
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

def generate_certificate(name:str):
    certificate_template_path = f'{directory}/assets/certificate_template.png'
    template = Image.open(certificate_template_path)
    draw = ImageDraw.Draw(template)
    font_name = 'ClashGrotesk-Semibold.ttf'
    font = ImageFont.truetype(font=f'{directory}/assets/{font_name}', size=32)
    color = (62, 62, 62)

    if len(name) > 20:
        name = name.split()
        if len(name) > 1:
            name = f"{name[0]} {name[1]}"
            if len(name) > 21:
                name = name.split()
                name = f"{name[0]} {name[1][0].capitalize()}"
        else:
            name = str(name[0])

    text_length = draw.textlength(name, font)
    x_pos = (template.width - text_length) / 2
    y_pos = 269
    
    draw.text((x_pos, y_pos), text=name, font=font, fill=color)
    out = BytesIO()
    template.save(out, format='PNG')
    return out

# GENERAL COMMANDS

@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        participant_data = get_participant_data(message.from_user.id)['fields']
        if participant_data['type'] in mentor_passcodes:
            bot.send_message(message.chat.id, f'''You have already completed registration as a *Mentor* 🧑‍🏫

*Here are your details:*
_Name: {participant_data['name']}_
_Station name: {participant_data['type'].capitalize()}_
_Participant ID: {participant_data['primary_key']}_

If you want to move to a different station, you can run /cleardata command to clear your current data from the database.''')
        elif participant_data['type'] == 'learner':
            bot.send_message(message.chat.id, f'''You have already completed registration as a *Learner* 🧑‍🎓

*Here are your details:*
_Name: {participant_data['name']}_
_Email: {participant_data['email']}_
_Participant ID: {participant_data['primary_key']}_
_No. of stations visited: {participant_data['visited_num']}_

If you wish to change any of your details, you can run /cleardata _(clears all your current data including your progress from our database)_ and then rerun the /start command''')
    except Exception as e:
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('🧑‍🏫 Mentor', callback_data='mentor'),
                InlineKeyboardButton('🧑‍🎓 Learner', callback_data='learner'))
        msg = bot.send_message(message.chat.id, "Welcome aboard *Learing Stations* @ Dyuksha '23 hosted by [TinkerHub NSSCE](https://linktr.ee/tinkerhubnssce), we're super excited to have you here 😁. I'm *BB8*, you're learning assistant. To get started you need to register yourself as a participant. So are you a *Mentor* or a *Learner*? \n\n_PS: I maybe a bit slow to respond at times, but I'm trying my best to reduce the latency, please bear with me if I seem slacking 🙂._", reply_markup=markup)

@bot.message_handler(commands=['visited'])
def visited_station(message):
    args = message.text.split(' ')
    if len(args) == 2:
        code = args[1]
        if validate_visitor_codes(code):
            station_name = validate_visitor_codes(code)
            try:
                record_id = get_record_id(message.from_user.id)
                learner_data = get_participant_data(message.from_user.id)['fields']
                if learner_data['type'] == 'learner':
                    visited_list = deserialize_list(learner_data['visited'])
                    if station_name not in visited_list:
                        visited_list.append(station_name)
                        update_visited(str(visited_list), len(visited_list), record_id)
                        if len(visited_list) < 10:
                            bot.send_message(message.chat.id, f"Yaay! you've succesfully visited the *{station_name}* station 🥁. {10 - len(visited_list)} stations left..")
                        else:
                            bot.send_message(message.chat.id, f"Yaay! you've succesfully visited the *{station_name}* station 🥁.")
                            certificate = generate_certificate(learner_data['name'])
                            certificate.seek(0)
                            markup = InlineKeyboardMarkup()
                            markup.row(InlineKeyboardButton('📥 Download as PNG', callback_data='download'))
                            bot.send_photo(message.chat.id, certificate, caption="Congratulations, you've visited all our stations 🎉. Here's a small token of appreciation for your efforts!", reply_markup=markup)
                            bb8_logger.info(f"{learner_data['name']} completed visiting all stations at {loggable_dt(datetime.utcnow())}")
                    else:
                        bot.send_message(message.chat.id, f"You've already visited the *{station_name}* station 👀. Please visit a different station.")
                else:
                    bot.send_message(message.chat.id, "You need to be a *Learner* 🎓 to run this command!")
            except Exception as e:
                bot.send_message(message.chat.id, "You need to register as a *Learner* 🎓 to run this command. Use the /start command to register first.")
        else:
            bot.send_message(message.chat.id, "Invalid visitor code ❌ Please ask your mentor for a valid one!")
    else:
        bot.send_message(message.chat.id, "*Correct usage: /visited <VISTOR CODE>*. Ask your mentor 🧑‍🏫 for the visitor code!")

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
            if participant_data['visited_num'] < 10:
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
        if participant_data['type'] == 'learner':
            visited_list = deserialize_list(participant_data['visited'])
            text = progress_as_text(visited_list, participant_data)
            bot.send_message(message.chat.id, text=text)
        else:
            bot.send_message(message.chat.id, "You need to register as a *Learner* 🎓 to run this command! Use the /start command to register first")
    except Exception as e:
        bot.send_message(message.chat.id, "You need to register as a *Learner* 🎓 to run this command! Use the /start command to register first")

# ADMIN ONLY COMMANDS

@bot.message_handler(commands=['listcodes'])
def list_codes(message):
    if message.from_user.id in admin_list:
        time_left = time.time() - start_time
        minutes_left = f"{int((randomise_interval//60 - 1) - time_left//60)}"
        seconds_left = f"{int(60 - time_left%60)}"
        text = f"_Time Remaining: {minutes_left}:{seconds_left}_\n\n"
        for station_name in visitor_codes:
            text += f"{station_name}: {visitor_codes[station_name]}\n"
        bot.send_message(message.chat.id, text)
        bb8_logger.info(f"{message.from_user.full_name} has used an admin command at {loggable_dt(datetime.utcnow())}")

@bot.message_handler(commands=['getinfo'])
def get_info(message):
    if message.from_user.id in admin_list:
        args = message.text.split(' ')
        if len(args) == 2:
            primary_key = int(args[1])
            try:
                participant_data = get_participant_data_by_key(primary_key)['fields']
                if participant_data['type'] in station_names:
                    text = f'''*Participant Data*

_Name: {participant_data['name']}_
_Type: {participant_data['type']}_
_User ID: {participant_data['tu_id']}_'''
                elif participant_data['type'] == 'learner':
                    text = f'''*Participant Data*

_Name: {participant_data['name']}_
_Type: {participant_data['type']}_
_User ID: {participant_data['tu_id']}_
_Email: {participant_data['email']}_
_No. of stations visited: {participant_data['visited_num']}_'''
                bot.send_message(message.chat.id, text)
                bb8_logger.info(f"{message.from_user.full_name} has used an admin command at {loggable_dt(datetime.utcnow())}")
            except Exception as e:
                bot.send_message(message.chat.id, "Participant not found ❌")

@bot.message_handler(commands=['regencert'])
def regenerate_cert(message):
    if message.from_user.id in admin_list:
        args = message.text.split(' ')
        if len(args) == 2:
            primary_key = args[1]
            try:
                participant_data = get_participant_data_by_key(primary_key)['fields']
                if participant_data['type'] == 'learner':
                    if participant_data['visited_num'] < 10:
                        bot.send_message(message.chat.id, "Learner has not visited all the stations!")
                        bb8_logger.info(f"{message.from_user.full_name} has used an admin command at {loggable_dt(datetime.utcnow())}")
                    else:
                        certificate = generate_certificate(participant_data['name'])
                        certificate.seek(0)
                        cert_name = participant_data['name'].split()[0].lower()
                        bot.send_photo(message.chat.id, certificate, caption=f"Certificate for *{cert_name.capitalize()}* has been regenerated on request ☑️.")
                        certificate.seek(0)
                        bot.send_document(message.chat.id, certificate, visible_file_name=f"{cert_name}_certificate.png")
                        bb8_logger.info(f"{message.from_user.full_name} has used an admin command at {loggable_dt(datetime.utcnow())}")
                else:
                    bot.send_message(message.chat.id, "Participant is not a learner ❌")
                    bb8_logger.info(f"{message.from_user.full_name} has used an admin command at {loggable_dt(datetime.utcnow())}")
            except Exception as e:
                bot.send_message(message.chat.id, "Participant not found ❌")
                bb8_logger.info(f"{message.from_user.full_name} has used an admin command at {loggable_dt(datetime.utcnow())}")

# NEXT STEP HANDLERS

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
        minutes_left = f"{int((randomise_interval//60 - 1) - time_left//60)}"
        seconds_left = f"{int(60 - time_left%60)}"
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('🔄 Refresh Code', callback_data='refresh'))
        bot.send_photo(message.chat.id, qr_img, caption=f"Hey there *{station_name}* mentor. Here's the visitor code for your station: *{code}* - the visitors may either type this code manually or scan the above qr to copy the code. This code expires in *{minutes_left}:{seconds_left}* minutes, hit _Refresh Code_ to get a new code.", reply_markup=markup)
        bb8_logger.info(f"{message.from_user.full_name} has registered as a Mentor at {loggable_dt(datetime.utcnow())}")
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
    msg = bot.send_message(message.chat.id, f"Okay *{name.split()[0]}*! Now tell me your email id. We'll use this for any further communication 📣 regarding our event")
    bot.register_next_step_handler(msg, process_email, name)

def process_email(message, name):
    global last_seen_message, last_seen_chat_id
    name = name
    type = 'learner'
    email = message.text
    learner_tu_id = str(message.from_user.id)
    add_new_record(name, type, learner_tu_id, email, "[]", 0)
    bot.send_message(message.chat.id, '''_That's all! Now you're all set to start learning 🏁. Here's what you need to do next:-_

- Visit any station you like, take all the time you need to learn about the specific domain.
- At the end of your learning session, the mentor at the station will give you a *visitor code* - a 6 digit alphanumeric code.
- Run the command /visited *<VISITOR CODE>* to mark the station as visited.
- You can either type the *vistor code* manually or scan the QR code displayed to copy it directly.
- Run the command /checkprogress anytime to check which stations you have/haven't visited so far.
- Finally, if you've visited all the stations I'll send you a cool *e-certificate* 🎁, that you can later showcase on your socials!

_So have you decided which station you're gonna visit first 👀?_''')
    bb8_logger.info(f"{name} has registered as a Learner at {loggable_dt(datetime.utcnow())}")
    if message.from_user.id in last_seen_chat_id:
        bot.delete_message(last_seen_chat_id[message.from_user.id], last_seen_message[message.from_user.id])
        last_seen_message.pop(message.from_user.id)
        last_seen_chat_id.pop(message.from_user.id)

# CALLBACK QUERY HANDLER

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global last_seen_chat_id, last_seen_chat_id, last_mentor_request
    if call.data == 'mentor':
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Go back', callback_data='back'))
        msg = bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Please enter your mentor passcode 🔑. Not a mentor? Hit *Go Back* and select the *Learner* option.", reply_markup=markup)
        last_seen_chat_id[call.from_user.id] = call.message.chat.id
        last_seen_message[call.from_user.id] = call.message.message_id
        last_mentor_request[call.from_user.id] = [call.message.chat.id, call.message.message_id]
        bot.register_next_step_handler(msg, process_passcode)
    elif call.data == 'learner':
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('Go back', callback_data='back'))
        msg = bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text='Hello there learner! What is your name?\n\n_Please type in your full name. This will be later on used to generate your certificate 📜_', reply_markup=markup)
        last_seen_chat_id[call.from_user.id] = call.message.chat.id
        last_seen_message[call.from_user.id] = call.message.message_id
        bot.register_next_step_handler(msg, process_name)
    elif call.data == 'back':
        if call.from_user.id in last_seen_chat_id:
            bot.clear_step_handler_by_chat_id(call.message.chat.id)
            last_seen_chat_id.pop(call.from_user.id)
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('🧑‍🏫 Mentor', callback_data='mentor'),
                   InlineKeyboardButton('🧑‍🎓 Learner', callback_data='learner'))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Welcome aboard *Learing Stations* @ Dyuksha '23 hosted by [TinkerHub NSSCE](https://linktr.ee/tinkerhubnssce), we're super excited to have you here 😁. I'm *BB8*, you're learning assistant. To get started you need to register yourself as a participant. So are you a *Mentor* or a *Learner*? \n\n_PS: I maybe a bit slow to respond at times, but I'm trying my best to reduce the latency, please bear with me if I seem slacking 🙂._", reply_markup=markup)
    elif call.data == 'refresh':
        mentor_tu_id = str(call.from_user.id)
        mentor_data = get_participant_data(mentor_tu_id)['fields']
        station_name = mentor_data['type']
        code = visitor_codes[station_name]
        qr_img = generate_qr(code)
        qr_img.seek(0)
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton('🔄 Refresh Code', callback_data='refresh'))
        time_left = time.time() - start_time
        minutes_left = f"{int((randomise_interval//60 - 1) - time_left//60)}"
        seconds_left = f"{int(60 - time_left%60)}"
        bot.edit_message_media(media=InputMediaPhoto(qr_img, caption=f"Here's the new visitor code for your station: {code} - the visitors may either type this code manually or scan the above qr to copy the code. This code expires in {minutes_left}:{seconds_left} minutes, hit Refresh Code to get a new code."), chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        msg = bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=f"Here's the new visitor code for your station: *{code}* - the visitors may either type this code manually or scan the above qr to copy the code. This code expires in *{minutes_left}:{seconds_left}* minutes, hit _Refresh Code_ to get a new code.", reply_markup=markup)
    elif call.data == 'yes':
        try:
            delete_last_record(call.from_user.id)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "Succesfully deleted all your data 🗑️. Run /start to register again.")
            bb8_logger.info(f"{call.from_user.full_name} has deleted all their data at {loggable_dt(datetime.utcnow())}")
        except:
            bot.delete_message(call.message.chat.id, call.message.message_id)
    elif call.data == 'no':
        bot.delete_message(call.message.chat.id, call.message.message_id)
    elif call.data == 'download':
        try:
            learner_data = get_participant_data(call.from_user.id)['fields']
            if learner_data['visited_num'] == 10:
                bot.edit_message_caption("Congratulations, you've visited all our stations 🎉. Here's a small token of appreciation for your efforts!", call.message.chat.id, call.message.message_id)
                certificate = generate_certificate(learner_data['name'])
                certificate.seek(0)
                cert_name = learner_data['name'].split()[0].lower()
                bot.send_document(call.message.chat.id, certificate, visible_file_name=f"{cert_name}_certificate.png")
            else:
                bot.edit_message_caption("Congratulations, you've visited all our stations 🎉. Here's a small token of appreciation for your efforts!", call.message.chat.id, call.message.message_id)
        except:
            pass

# RUN BOT

if __name__ == '__main__':
    threading.Thread(target=bot.infinity_polling, name='bot_infinity_polling', daemon=True).start()
    bb8_logger.info(f"{bot.user.full_name} is logged in as @{bot.user.username}")
    randomise_visitor_codes()
    while True:
        schedule.run_pending()
        time.sleep(1)
