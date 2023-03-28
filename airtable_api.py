import os
import configparser
from pyairtable import Table
from pyairtable.formulas import match

directory = os.path.dirname(os.path.realpath(__file__))
config = configparser.ConfigParser()
config.read(f'{directory}/config.ini')

api_key = str(config.get("airtable", "api_key"))
base_id = str(config.get("airtable", "base_id"))
table_name = str(config.get("airtable", "table_name"))

table = Table(api_key, base_id, table_name)

def add_new_record(name:str, type:str, tu_id:str, email:str = "", visited:str = "[]"):
    data = {'name': name,
            'type':type,
            'tu_id':tu_id,
            'email':email,
            'visited':visited}
    table.create(data)

def get_record_id(tu_id:str):
    try:
        record = table.first(formula=match({"tu_id":tu_id}), sort=["-primary_key"])
        record_id = record['id']
    except Exception as e:
        return e
    return record_id

def get_participant_data(tu_id:str):
    try:
        participant = table.first(formula=match({"tu_id":tu_id}), sort=["-primary_key"])
    except Exception as e:
        return e
    return participant

def update_visited(visited:str, record_id:str):
    try:
        table.update(record_id, {"visited":visited})
    except Exception as e:
        return e

# def delete_duplicate_records(tu_id:str):
#     try:
#         matches = table.all(formula=match({"tu_id":tu_id}), sort=["-primary_key"])
#         duplicates = matches[1:]
#         duplicate_ids = [duplicate['id'] for duplicate in duplicates]
#         table.batch_delete(duplicate_ids)
#     except Exception as e:
#         return e

def delete_last_record(tu_id:str):
    try:
        match_record = table.first(formula=match({"tu_id":tu_id}), sort=["-primary_key"])
        match_id = match_record['id']
        table.delete(match_id)
    except Exception as e:
        return e