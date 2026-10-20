"""Desktop-session launcher; service never needs access to the graphical session."""
import time
import urllib.request
import webbrowser


def main():
    url = 'http://127.0.0.1:8765/'
    for _ in range(120):
        try:
            with urllib.request.urlopen(url + 'api/state', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return 0
        except OSError:
            pass
        time.sleep(2)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
