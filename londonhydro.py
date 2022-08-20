#!/usr/bin/python3
"""
London Hydro Monitor.

Monitors your energy usage.

TODO Calculate data dynamically
TODO See if we can request ONLY one hour
TODO Store credentials elsewhere
"""
import sys
import logging
import json
import smtplib

from datetime import datetime, timedelta
from argparse import ArgumentParser

# import http.client as http_client
# http_client.HTTPConnection.debuglevel = 1

import requests
import pandas

LOG_FORMAT = '%(asctime)-15s [%(funcName)s] %(message)s'

CSV_FILE = '/tmp/londonhydro.csv'
LOGIN_URL = 'https://iamapi-dot-lh-myaccount-prod.appspot.com/iam/api/login'
USAGE_URL_FMT = 'https://api-dot-lh-myaccount-prod.appspot.com/api/v1/greenButton/E{}/downloadData'
SMTP_SERVER = 'smtp.gmail.com'

def login(username, password):
    """
    Login with London Hydro
    """
    data = {
        'username': username,
        'password': password,
        'applicationCode': 'MY',
        'applicationUrl': 'https://www2.londonhydro.com/site/myaccount/',
        'client_id': 'LondonHydroApp'
    }

    resp = requests.post(LOGIN_URL, data=data)
    if resp.status_code != 200:
        logging.error('Unable to login (%d) "%s"', resp.status_code, resp.content)
        sys.exit(1)

    try:
        js_data = json.loads(resp.content)
    except json.JSONDecodeError as err:
        logging.error('Unable to parse login response "%s"', err)
        sys.exit(1)

    token = js_data['access_token']
    token_type = js_data['token_type']

    logging.debug('Login Succesful (%s %s)', token_type, token)
    return (token_type, token)


def get_start_end():
    """
    Get the desired start and end time.
    """
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_ts = int(now.timestamp())
    now = now - timedelta(days=1)
    start_ts = int(now.timestamp())
    return (start_ts, end_ts)


def get_usage_data(account, token_type, token_value, start_ts, end_ts):
    """
    Download usage data in CSV format.
    """
    params = {
        'startDate': start_ts * 1000,
        'endDate': end_ts * 1000,
        'greenButton': 'true',
        'fmt': 'text/csv',
        'ck': '1660772144033'}
    headers = {
      'Authorization': f'{token_type} {token_value}',
      'Accept': 'text/csv'
    }
    url = USAGE_URL_FMT.format(account)
    resp = requests.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        logging.error('Unable to get usager data (%s) "%s"', resp.status_code, resp.content)
        sys.exit(1)

    with open(CSV_FILE, 'wb') as file:
        file.write(resp.content)


def load_csv():
    """
    Read the CSV data and cleanup the dataframe.
    """
    # Read the CSV data
    dframe = pandas.read_csv(CSV_FILE)

    # Remove the junk headers
    dframe.columns = dframe.iloc[3].tolist()

    # reset the index after cutting out rows
    dframe = dframe.drop(dframe.index[0:4]).reset_index(drop=True)

    # split out the start and end
    x = dframe[dframe.columns[0]].str.split(' to ', expand=True)
    x.columns = ['start', 'end']
    dframe = dframe.join(x)

    # reorganize columns
    columns = ['start', 'end']
    columns.extend(dframe.columns[1:3].tolist())
    dframe = dframe[columns]

    dframe['start'] = dframe[['start']].apply(lambda x: datetime.strptime(x[0], '%Y/%m/%d %H:%M').timestamp(), axis=1)
    dframe['end'] = dframe[['end']].apply(lambda x: datetime.strptime(x[0], '%Y/%m/%d %H:%M').timestamp(), axis=1)
    kwh = dframe.columns[2]
    dframe[kwh] = dframe[[kwh]].apply(lambda x: float(x[0]), axis=1)
    return dframe


def get_stats(dframe):
    column = dframe.columns[2]
    total_kwh = dframe[column].sum()
    avg_kwh = dframe[column].mean()
    max_kwh = dframe.iloc[dframe[column].idxmax()]
    max_value = max_kwh[column]
    max_start = datetime.fromtimestamp(max_kwh[dframe.columns[0]]).isoformat()
    max_end = datetime.fromtimestamp(max_kwh[dframe.columns[1]]).isoformat()
    stats = {
        'average': avg_kwh,
        'total': total_kwh,
        'max': {
            'start': max_start,
            'end': max_end,
            'value': max_value
        }
    }
    return stats


def trim_dataframe(untrimmed, start_ts, end_ts):
    """
    Trim data in a dataframe between two timestamps
    """
    start_trim = untrimmed[untrimmed['start'] >= start_ts]
    return start_trim[start_trim['end'] <= end_ts]


def send_notification(stats, gmail, token):
    subject = 'London Hydro Daily Usage'
    avg = '{:.2f}'.format(stats['average'])
    maxm = '{:.2f}'.format(stats['max']['value'])
    start = stats['max']['start']
    end = stats['max']['end']
    total = '{:.2f}'.format(stats['total'])
    body = f'Average Usage: {avg}kW\nMaximum Usage: {maxm}kW ({start} - {end})\nTotal Usage: {total} kWh'

    msg = 'Subject: {}\n\n{}'.format(subject, body)

    server = smtplib.SMTP(SMTP_SERVER, 587)
    server.ehlo()
    server.starttls()
    server.login(gmail, token)
    server.sendmail(f'{gmail}@gmail.com', 'micahgalizia@gmail.com', msg)
    server.quit()
    logging.info('EMail sent')
    pass

def __main__():
    # Parse arguments
    parser = ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true', dest='debug',
                        help='debug logging')
    parser.add_argument('-e', '--electrical', action='store', dest='electrical', required=True,
                        help='London Hydro electrical account number')
    parser.add_argument('-u', '--username', action='store', dest='username', required=True,
                        help='London Hydro username')
    parser.add_argument('-p', '--password', action='store', dest='password', required=True,
                        help='London Hydro password')
    parser.add_argument('-g', '--gmail', action='store', dest='gmail',
                        help='GMail address to send mail from')
    parser.add_argument('-t', '--token', action='store', dest='token',
                        help='GMail SMTP token')
    args = parser.parse_args()

    # Initialize Logs
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format=LOG_FORMAT, level=log_level)

    (tok_t, tok) = login(args.username, args.password)
    (start, end) = get_start_end()
    get_usage_data(args.electrical, tok_t, tok, start, end)
    data_frame = load_csv()
    data_frame = trim_dataframe(data_frame, start, end)
    stats = get_stats(data_frame)
    logging.info('Emailing stats...')

    if args.gmail and args.token:
        send_notification(stats, args.gmail, args.token)
    else:
        logging.info('Not emailing...')

if __name__ == '__main__':
    __main__()
