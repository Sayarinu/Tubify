"""One-shot local API example. Pairing code and token are never printed or saved."""
from getpass import getpass
import http.client
import json


def main():
    port = int(input('Local API port [9864]: ').strip() or '9864')
    if not 1024 <= port <= 65535:
        raise ValueError('Invalid port')
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        conn.request('POST', '/v1/pair', json.dumps({'code': getpass('One-time pairing code: ')}), {'Content-Type': 'application/json'})
        response = conn.getresponse()
        data = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError('Pairing failed. Check the app and generate a new code.')
        conn.request('GET', '/v1/state', headers={'Authorization': 'Bearer ' + data['token']})
        response = conn.getresponse()
        state = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError('State request failed. Check client permission in the app.')
        print('Playback:', state['playback']['state'])
        print('Title:', (state.get('track') or {}).get('title', 'No track'))
        print('Revoke this example client in Local API settings when finished.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
