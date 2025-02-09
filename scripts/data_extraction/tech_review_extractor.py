import os
import json
import yake
import re
import spacy
import string
import threading
import contractions
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up YouTube API key
YT_API_KEY = 'AIzaSyDHVMn_VngdOBXK5ATfJWv3ybLHPpUeeVY'

# Load spaCy model
nlp = spacy.load("en_core_web_lg")

# Add this mapping at the beginning of your script
CATEGORY_ID_MAP = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "18": "Short Movies",
    "19": "Travel & Events",
    "20": "Gaming",
    "21": "Videoblogging",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
    "30": "Movies",
    "31": "Anime/Animation",
    "32": "Action/Adventure",
    "33": "Classics",
    "34": "Comedy",
    "35": "Documentary",
    "36": "Drama",
    "37": "Family",
    "38": "Foreign",
    "39": "Horror",
    "40": "Sci-Fi/Fantasy",
    "41": "Thriller",
    "42": "Shorts",
    "43": "Shows",
    "44": "Trailers"
}

channel_stats_cache = {}
channel_stats_lock = threading.Lock()

def extract_keywords(text, num_keywords=20, language='en'):
    """Extract a list of high-quality keywords from the given text using YAKE"""
    if text == "No transcript available":
        return []

    try:
        # Preprocess text for better extraction

        # Remove filler words
        filler_words = {
            'um', 'uh', 'you know', 'like', 'i mean', 'sort of', 'kind of',
            'basically', 'actually', 'so', 'well', 'right', 'just', 'anyway'
        }
        doc = nlp(text)
        processed_sentences = []

        for sent in doc.sents:
            tokens = []
            skip_next = False

            for i, token in enumerate(sent):
                if skip_next:
                    skip_next = False
                    continue

                # Check if the current token is a filler word with the appropriate POS
                if token.lower_ in filler_words and token.pos_ in {'INTJ', 'DISCOURSE'}:
                    # Remove preceding punctuation if it exists
                    if tokens and tokens[-1].strip() in string.punctuation:
                        tokens.pop()
                        if tokens:
                            tokens[-1] = tokens[-1] + ' '
                    
                    # Check if the next token is punctuation and skip it
                    if i + 1 < len(sent) and sent[i + 1].is_punct:
                        skip_next = True
                    continue  # Skip the filler word itself

                # Append the token text with its whitespace
                tokens.append(token.text_with_ws)
            
            if tokens:
                sentence = ''.join(tokens).strip()
                processed_sentences.append(sentence)

        text = ' '.join(processed_sentences)

        text = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', '', text)
        text = re.sub(r'-', '', text)
        text = contractions.fix(text)  # Expand contractions

        max_ngram_size = 3
        deduplication_threshold = 0.9
        numOfKeywords = num_keywords

        kw_extractor = yake.KeywordExtractor(
            lan=language,
            n=max_ngram_size,
            dedupLim=deduplication_threshold,
            dedupFunc='seqm',
            windowsSize=2,
            top=numOfKeywords
        )

        keywords = kw_extractor.extract_keywords(text)
        return [kw[0] for kw in keywords]
    except Exception as e:
        print(f"Error extracting keywords: {e}")
        return []

def extract_entities(text):
    """Use spaCy to extract named entities from the given text."""
    if text == "No transcript available":
        return []

    try:
        doc = nlp(text)
        entities = list(set([(ent.text, ent.label_) for ent in doc.ents]))
        return entities
    except Exception as e:
        print(f"Error extracting entities: {e}")
        return []

def process_transcript(text):
    if text == "No transcript available":
        return text

    """
    Cleans the input text by removing:
    - Non-ASCII characters
    - Line breaks
    - Unnecessary whitespace
    """
    # 3. Remove non-ASCII characters
    cleaned = re.sub(r'[^\x00-\x7F]+', '', text)
    
    # 4. Remove line breaks (\n and \r)
    cleaned = re.sub(r'[\n\r]+', ' ', cleaned)
    
    # 5. Remove unnecessary whitespace (multiple spaces, tabs, etc.)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned

def get_manual_transcript(video_id):
    """Extract the manually generated transcript of the YouTube video in 'en' or 'en-US'."""
    try:
        # Get the list of available transcripts
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Filter for manually created transcripts in 'en' or 'en-US'
        manual_transcripts = [t for t in transcript_list if not t.is_generated and t.language_code in ['en', 'en-US']]
        
        if manual_transcripts:
            # Fetch the first available manually created transcript in 'en' or 'en-US'
            transcript = manual_transcripts[0].fetch()
            return ' '.join(entry['text'] for entry in transcript)
        else:
            return "No manual transcript available"
        
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        print(f"No transcript available for video ID '{video_id}': {e}")
        return "No transcript available"
    except Exception as e:
        print(f"Error fetching transcript for video ID '{video_id}': {e}")
        return "No transcript available"

def extract_urls(text):
    """Extract all URLs from the given text."""
    if not text:
        return []
    try:
        url_pattern = r'(https?://[^\s]+)'
        urls = re.findall(url_pattern, text)
        return [url.split('&')[0] for url in urls]  # Clean URLs
    except Exception as e:
        print(f"Error extracting URLs: {e}")
        return []

def get_video_metadata(video_id):
    """Fetch metadata about the YouTube video using YouTube API"""
    default_metadata = {
        "title": "Unknown Title",
        "channel": "Unknown Channel",
        "channel_id": "Unknown Channel ID",
        "subscriber_count": 0,
        "upload_date": "Unknown Date",
        "description": "No description available",
        "tags": [],
        "views": 0,
        "likes": 0,
        "comments_count": 0,
        "category": "Unknown Category"
    }

    try:
        # Create a new YouTube service object per thread to ensure thread safety
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)

        # Fetch video data
        video_response = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
        if not video_response.get('items'):
            print(f"No metadata found for video ID: {video_id}")
            return default_metadata

        video_item = video_response['items'][0]
        video_snippet = video_item.get('snippet', {})
        video_stats = video_item.get('statistics', {})

        # Use the hardcoded mapping
        category_id = video_snippet.get('categoryId', '')
        category_title = CATEGORY_ID_MAP.get(category_id, "Unknown Category")

        channel_id = video_snippet.get('channelId', default_metadata['channel_id'])

        # Fetch channel data or use cache
        with channel_stats_lock:
            if channel_id in channel_stats_cache:
                channel_stats = channel_stats_cache[channel_id]
            else:
                # Fetch channel data
                channel_response = youtube.channels().list(part="statistics", id=channel_id).execute()
                channel_stats = channel_response.get('items', [{}])[0].get('statistics', {})
                # Store in cache
                channel_stats_cache[channel_id] = channel_stats

        return {
            "title": video_snippet.get('title', default_metadata['title']),
            "channel": video_snippet.get('channelTitle', default_metadata['channel']),
            "channel_id": channel_id,
            "subscriber_count": int(channel_stats.get('subscriberCount', 0)),
            "upload_date": video_snippet.get('publishedAt', default_metadata['upload_date']),
            "description": video_snippet.get('description', default_metadata['description']),
            "tags": video_snippet.get('tags', default_metadata['tags']),
            "views": int(video_stats.get('viewCount', 0)),
            "likes": int(video_stats.get('likeCount', 0)),
            "comments_count": int(video_stats.get('commentCount', 0)),
            "category": category_title
        }

    except HttpError as e:
        print(f"HTTP error occurred while fetching metadata for video ID '{video_id}': {e}")
    except Exception as e:
        print(f"Error fetching metadata for video ID '{video_id}': {e}")

    return default_metadata

def create_json_document(video_id):
    """Full pipeline: from YouTube video id to JSON file creation"""
    metadata = get_video_metadata(video_id)

    description_text = metadata['description']
    description_links = extract_urls(description_text)

    transcript_text = get_manual_transcript(video_id)
    transcript_text = process_transcript(transcript_text)
    transcript_entities = extract_entities(transcript_text)
    transcript_keywords = extract_keywords(transcript_text)

    json_document = {
        "video_id": video_id,
        "title": metadata["title"],
        "channel": metadata["channel"],
        "channel_id": metadata["channel_id"],
        "subscriber_count": metadata["subscriber_count"],
        "upload_date": metadata["upload_date"],
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "category": metadata["category"],
        "tags": metadata["tags"],
        "views": metadata["views"],
        "likes": metadata["likes"],
        "comments_count": metadata["comments_count"],
        "description": description_text,
        "description_links": description_links,
        "transcript": transcript_text,
        "transcript_keywords": transcript_keywords,
        "transcript_entities": transcript_entities
    }

    channel = metadata["channel"]
    folder_path = os.path.join("tech_videos_json", channel)
    os.makedirs(folder_path, exist_ok=True)

    json_file_path = os.path.join(folder_path, f"{video_id}.json")
    try:
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_document, f, indent=4, ensure_ascii=False)
        print(f"JSON document created at: {json_file_path}")
    except Exception as e:
        print(f"Error writing JSON file '{json_file_path}': {e}")

def fetch_videos_with_captions(channel_id, max_videos=750):
    youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
    
    try:
        # Get the uploads playlist ID
        channel_response = youtube.channels().list(part='contentDetails', id=channel_id).execute()
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        videos_with_captions = []
        next_page_token = None
        
        while len(videos_with_captions) < max_videos:
            # Fetch video IDs from the uploads playlist
            playlist_response = youtube.playlistItems().list(
                part='contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()
            
            video_ids = [item['contentDetails']['videoId'] for item in playlist_response.get('items', [])]
            
            if not video_ids:
                break
            
            # Fetch video details to check for captions
            video_response = youtube.videos().list(
                part='contentDetails',
                id=','.join(video_ids)
            ).execute()
            
            for item in video_response.get('items', []):
                if item['contentDetails'].get('caption') == 'true':
                    videos_with_captions.append(item['id'])
                    if len(videos_with_captions) >= max_videos:
                        return videos_with_captions
            
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break
        
        return videos_with_captions
    
    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    
    return []

def process_channel(channel_id):
    """Process the top 500 most viewed videos from a YouTube channel concurrently"""
    video_ids = fetch_videos_with_captions(channel_id)
    if not video_ids:
        print(f"No videos with manually generated captions found for channel ID: {channel_id}")
        return

    max_workers = 15  # Adjust the number of threads as needed
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_video_id = {executor.submit(create_json_document, vid): vid for vid in video_ids}
        for future in as_completed(future_to_video_id):
            video_id = future_to_video_id[future]
            try:
                future.result()
            except Exception as e:
                print(f"Exception occurred while processing video '{video_id}': {e}")

if __name__ == "__main__":
    # Example channel ID for testing
    channel_ids = [
            # "UCBJycsmduvYEL83R_U4JriQ",      # MKBHD
            #"UCXuqSBlHAE6Xw-yeJA0Tunw",      # LTT
            #"UCsTcErHg8oDvUnTzoqsYeNw",      # Unbox Therapy
            #"UCVYamHliCI9rw1tHR1xbkfw",      # Dave2D
            #"UCXGgrKt94gR6lmN4aN3mYTg",    # Austin Evans
            #"UCWFKCr40YwOZQx8FHU_ZqqQ",    # JerryRigEverything
            #"UCey_c7U86mJGz1VJWH5CYPA",    # Ijustine
            #"UCddiUEpeqJcYeBxX1IVBKvQ",    # The Verge
            #"UCDlQwv99CovKafGvxyaiNDA",    # Jonathan Morrison
            #"UCSOpcUkE-is7u7c4AkLgqTw",    # MrMobile
            #"UC0vBXGSyV14uvJ4hECDOl0Q",    # Techquickie
            #"UCdBK94H6oZT2Q7l0-b0xmMg",    # Short Circuit
            #"UCeeFfhMcJa1kjtfZAGskOCA",    # Techlinked
            #"UC1IQIspOkCeV3WnYm32SBFQ",    # This is
            #"UCdp6GUwjKscp5ST4M4WgIpw",    # Tech Wiser
            #"UCO2x-p9gg9TLKneXlibGR7w",    # Snazzy Labs
            #"UCEp20NgOZHmgWdbQdHSxgjw",    # This Does Not Compute
            #"UCy0tKL1T7wFoYcxCe0xjN6Q",    # Technology Connection
            #"UCQ6fPy9wr7qnMxAbFOGBaLw",    # Computer Clan
            #"UCUQo7nzH1sXVpzL92VesANw",    # DIY Perks
            #"UCvcRA2Hva1lULVf4GCouH8w",    # Dawid
            #"UCmbkRUS_4Efdt5UIhwNqtcw",    # Greg Salazar
            #"UCP7WmQ_U4GB3K51Od9QvM0w",    # Tom Bombal
            #"UCTzLRZUgelatKZ4nyIKcAbg"     # Hardware Canucks
    ]

    for channel_id in channel_ids:
        process_channel(channel_id)
