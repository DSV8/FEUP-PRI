import os
import json
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
from collections import defaultdict

# Path to the folder containing channel folders
base_path = './tech_videos_json'

# Path to the statistics folder
statistics_path = './statistics'

# Create the statistics folder if it doesn't exist
os.makedirs(statistics_path, exist_ok=True)

# Initialize lists to store data
documents = []
channels = set()
upload_dates = []
subscriber_counts = []
views = []
likes = []
comments_counts = []

# Function to collect data from JSON files
def collect_data_from_json(json_file):
    with open(json_file, 'r') as f:
        data = json.load(f)
        documents.append(data)
        upload_dates.append(data['upload_date'])
        channels.add(data['channel'])
        subscriber_counts.append(data['subscriber_count'])
        views.append(data['views'])
        likes.append(data['likes'])
        comments_counts.append(data['comments_count'])

# Walk through the base directory to process all JSON files
for root, _, files in os.walk(base_path):
    for file in files:
        if file.endswith('.json'):
            collect_data_from_json(os.path.join(root, file))

# Total number of documents
total_documents = len(documents)

# Largest and smallest document (by size in characters)
largest_document = max(documents, key=lambda d: len(json.dumps(d)))
smallest_document = min(documents, key=lambda d: len(json.dumps(d)))

# Convert upload_dates to datetime
df = pd.DataFrame(documents)
df['upload_date'] = pd.to_datetime(df['upload_date'])

# Earliest and latest upload dates
earliest_date = df['upload_date'].min()
latest_date = df['upload_date'].max()

# Number of videos per year
videos_per_year = df['upload_date'].dt.year.value_counts().sort_index()

# Visualization: Number of videos per year
plt.figure(figsize=(10, 6))
videos_per_year.plot(kind='bar', color='skyblue')
plt.title('Number of Videos Per Year')
plt.xlabel('Year')
plt.ylabel('Number of Videos')
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'videos_per_year.png'))
plt.close()

# Number of unique channels
unique_channels = df['channel'].nunique()

# Number of videos per channel
videos_per_channel = df['channel'].value_counts()

# Visualization: Number of videos per channel
plt.figure(figsize=(10, 6))
videos_per_channel.plot(kind='bar', color='salmon')
plt.title('Number of Videos Per Channel')
plt.xlabel('Channel')
plt.ylabel('Number of Videos')
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'videos_per_channel.png'))
plt.close()

# Descriptive statistics for numeric fields
numeric_data = pd.DataFrame({
    'subscriber_count': df['subscriber_count'],
    'views': df['views'],
    'likes': df['likes'],
    'comments_count': df['comments_count']
})

# Calculate statistics
stats = numeric_data.describe(percentiles=[.25, .5, .75, .95])

# Visualization: Distribution of numeric fields
numeric_data.hist(figsize=(10, 10), bins=20, color='lightgreen')
plt.suptitle('Distributions of Subscriber Count, Views, Likes, Comments Count')
plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig(os.path.join(statistics_path, 'numeric_distributions.png'))
plt.close()

# Aggregate data by month
monthly_data = df.resample('ME', on='upload_date').agg({
    'views': 'sum',
    'likes': 'sum',
    'comments_count': 'sum'
}).reset_index()

# Visualization: Views Over Time (Monthly)
plt.figure(figsize=(12, 6))
plt.plot(monthly_data['upload_date'], monthly_data['views'], label='Views', color='blue')
plt.title('Monthly Views Over Time')
plt.xlabel('Month')
plt.ylabel('Total Views')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'monthly_views_over_time.png'))
plt.close()

# Visualization: Engagement Over Time (Monthly)
plt.figure(figsize=(12, 6))
plt.plot(monthly_data['upload_date'], monthly_data['likes'], label='Likes', color='green')
plt.plot(monthly_data['upload_date'], monthly_data['comments_count'], label='Comments', color='orange')
plt.title('Monthly Engagement Over Time (Likes and Comments)')
plt.xlabel('Month')
plt.ylabel('Total Engagement')
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'monthly_engagement_over_time.png'))
plt.close()

# Visualization: Subscriber Count vs Views
plt.figure(figsize=(10, 6))
plt.scatter(df['subscriber_count'], df['views'], alpha=0.5, color='blue')
plt.title('Subscriber Count vs Views')
plt.xlabel('Subscriber Count')
plt.ylabel('Views')
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'subscriber_vs_views.png'))
plt.close()

# Visualization: Subscriber Count vs Likes and Comments
plt.figure(figsize=(10, 6))
plt.scatter(df['subscriber_count'], df['likes'], label='Likes', alpha=0.5, color='green')
plt.scatter(df['subscriber_count'], df['comments_count'], label='Comments', alpha=0.5, color='orange')
plt.title('Subscriber Count vs Likes and Comments')
plt.xlabel('Subscriber Count')
plt.ylabel('Likes and Comments')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'subscriber_vs_likes_comments.png'))
plt.close()

# Initialize lists for entities
all_entities = []

# Aggregate keywords and entities from each document
for doc in documents:
    for entity, entity_type in doc['transcript_entities']:
        all_entities.append((entity, entity_type))

# Create a dictionary to store the most common entity for each category
entity_by_category = defaultdict(list)

# Aggregate entities based on their category
for entity, entity_type in all_entities:
    entity_by_category[entity_type].append(entity)

# Find the most common entity in each category
most_common_entity_per_category = {
    category: Counter(entities).most_common(1)[0]
    for category, entities in entity_by_category.items()
}

# Visualization: Most Common Entity in Each Category
categories = list(most_common_entity_per_category.keys())
entities = [item[0] for item in most_common_entity_per_category.values()]
frequencies = [item[1] for item in most_common_entity_per_category.values()]

plt.figure(figsize=(10, 6))
plt.barh(categories, frequencies, color='skyblue')
for index, value in enumerate(frequencies):
    plt.text(value, index, f'{entities[index]} ({value})', va='center')

plt.title('Most Common Entity in Each Category')
plt.xlabel('Occurrences')
plt.ylabel('Entity Category')
plt.tight_layout()
plt.savefig(os.path.join(statistics_path, 'most_common_entity_per_category.png'))
plt.close()

# Store statistics in a readable format in a text file
statistics_summary_path = os.path.join(statistics_path, 'statistics_summary.txt')
with open(statistics_summary_path, 'w') as f:
    f.write(f"Total number of documents: {total_documents}\n")
    f.write(f"Largest document: {largest_document['video_url']}\n")
    f.write(f"Smallest document: {smallest_document['video_url']}\n")
    f.write(f"Earliest upload date: {earliest_date.strftime('%Y-%m-%d')}\n")
    f.write(f"Latest upload date: {latest_date.strftime('%Y-%m-%d')}\n")
    f.write(f"Number of unique channels: {unique_channels}\n")
    f.write(f"Videos per channel:\n{videos_per_channel.to_string()}\n\n")
    f.write(f"Descriptive statistics for numeric fields:\n{stats.to_string()}\n")
    f.write("\nMost Common Entity in Each Category:\n")
    for category, (entity, count) in most_common_entity_per_category.items():
        f.write(f"{category}: {entity} ({count} occurrences)\n")

print(f"Statistics have been saved to the '{statistics_path}' folder and visualizations generated.")
