import youtube_dl
from sortedcollections import ValueSortedDict

class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)

def my_hook(d):
    if d['status'] == 'finished':
        print('Done downloading, now converting ...')

def get_video_info(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'logger': MyLogger(),
        'progress_hooks': [my_hook],
        'extract_flat': True,  # To get metadata without downloading
        'skip_download': True  # Avoid downloading the actual video
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)
    return result

def sort_videos_by_likes(playlist_url):
    playlist_info = get_video_info(playlist_url)
    if 'entries' not in playlist_info
