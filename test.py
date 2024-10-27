import yt_dlp
import re
import yandex_music
import requests
from json import loads
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry



def upload(filename, target, log_file):
    print() # После скачивания нет переноса каретки
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 501, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    try:
        with open(filename, "rb") as f:
            files = {"file": (filename, f, "audio/mp3")}
            r = session.post(url=target, files=files, timeout=30, verify=False)
            r.raise_for_status()
        print(loads(r.text))
        log_file.write(str(loads(r.text))+'\n')
    except requests.exceptions.SSLError as e:
        print(f'SSL ошибка: {e}')
        log_file.write(f'SSL ошибка: {e}\n')
    except requests.exceptions.Timeout:
        print(f'Запрос превысил 30 секунд.')
        log_file.write(f'Запрос превысил 30 секунд.\n')
    except requests.exceptions.RequestException as e:
        print(f'Произошла ошибка: {e}')
        log_file.write(f'Произошла ошибка: {e}\n')


def get_target(title, kind):
    global token
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://music.yandex.ru/handlers/ugc-upload.jsx?kind={kind}&filename={title}" # kind=3 is a favourite`s id playlist

    return loads(requests.get(url, headers=headers).text).get("post-target")


def progress_hook(d, title, kind, log_file):
    if d['status'] == 'finished':
        target = get_target(title, kind)
        upload(d['filename'], target, log_file)


def send(url, title, kind, log_file):
    ydl_opts = {
        'outtmpl': f'{title}.%(ext)s', # output template to name files as <title>.<ext>
        'paths': {'home': 'output'}, # temp and main files in one folder
        'format': 'ba[ext=m4a]', # bestaudio.m4a
        'retries': 5,
        'quiet': True, # without logs
        'progress': True, # show progress bar
        'skip_unavailable_fragments': True,
        'noincludeunavailablevideos': True,
        'ignoreerrors': True,
        'no_warnings': True,
        'progress_hooks': [lambda d: progress_hook(d, title, kind, log_file)],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def add_songs_to_playlist(token, playlist_name, songs_dict, log_file_path):
    client = yandex_music.Client(token).init()

    # Поиск или создание плейлиста
    playlists = client.users_playlists_list()
    playlist = next((p for p in playlists if p.title == playlist_name), None)

    if playlist is None:
        playlist = client.users_playlists_create(title=playlist_name)
        print(f"Создан новый плейлист: {playlist_name}")

    # Получение ID плейлиста
    playlist_id = playlist.kind
    user_id = playlist.owner.uid

    with open(log_file_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"\nФайл открыт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        # Добавление песен в плейлист
        for key in songs_dict:
            title = songs_dict[key]['title']
            url = songs_dict[key]['url']
            search_results = client.search(title)
            if search_results.best:
                result = search_results.best.result
                if isinstance(result, yandex_music.Track):
                    # Получаем актуальную ревизию плейлиста
                    playlist = client.users_playlists(kind=playlist_id, user_id=user_id)
                    revision = playlist.revision

                    # Добавляем трек в плейлист
                    client.users_playlists_insert_track(
                        kind=playlist_id,
                        track_id=result.id,
                        album_id=result.albums[0].id,
                        revision=revision,
                        user_id=user_id
                    )
                    log_file.write(f"{key}) Добавлено: {title}\n")
                    print(f"{key}) Добавлено: {title}")
                else:
                    log_file.write(f"{key}) Найдено, но не является треком: {title}\n")
                    print(f"{key}) Найдено, но не является треком: {title}")
                    send(url, title, playlist_id, log_file)
            else:
                log_file.write(f"{key}) Не найдено: {title}\n")
                print(f"{key}) Не найдено: {title}")
                send(url, title, playlist_id, log_file)


def clean_titles(songs_dict):
    for key in songs_dict:
        temp_value = songs_dict[key]['title']

        temp_value = re.sub(r'[\(\[\{].*?[\)\]\}]', '', temp_value, flags=re.IGNORECASE)
        temp_value = re.sub(r'\b(official|mv|performance|ver\.?|original)\b', '', temp_value, flags=re.IGNORECASE)
        temp_value = ' '.join(temp_value.split()).strip()

        songs_dict[key]['title'] = temp_value


def get_songs_dict(url, skip=0, n=-1):
    ydl_opts = {
        'playliststart': skip,
        'quiet': True,
        'extract_flat': True,  # Извлекает только метаданные, без загрузки видео
        'playlistend': skip+n,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        video_list = info_dict.get('entries', [])

        songs_dict = { i: {'title': video['title'], 'url': video['url']} for i, video in enumerate(video_list) }

    return songs_dict


if __name__ == '__main__':
    token = ''
    playlist_url = "https://www.youtube.com/playlist?list=PLcLWzrwuuZhP-qE-ttdWn0x8ANgR8xzpC"
    log_file_path = 'log.txt'
    playlist_name = 'test'

    songs_dict = get_songs_dict(playlist_url)

    clean_titles(songs_dict)

    add_songs_to_playlist(token, playlist_name, songs_dict, log_file_path)
