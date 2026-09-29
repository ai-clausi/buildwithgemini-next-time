import datetime
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-63911e77f35b"
COLLECTION_NAME = "experiences"

db = firestore.Client(project=PROJECT_ID)

seed_data = [
    {
        "id": "exp-travel-usa-shirts",
        "category": "travel",
        "title": "14-day USA trip packing lessons",
        "situation": "Packing for a 14-day vacation to the USA",
        "lesson": "Packed 7 t-shirts, which was too many because laundry was easily accessible and I bought new clothes there.",
        "next_time_advice": "Pack at most 4-5 versatile t-shirts for 2-week trips if laundry or shopping is planned.",
        "tags": ["travel", "packing", "clothing", "usa"],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "exp-health-late-pizza",
        "category": "health",
        "title": "Late dinner pizza and poor sleep",
        "situation": "Ate a heavy pizza dinner at 19:00 / 7 PM",
        "lesson": "Had significantly worse sleep and restless night after eating heavy greasy food late in the evening.",
        "next_time_advice": "Eat dinner before 18:00 or choose lighter meals if eating after 18:30 for better sleep quality.",
        "tags": ["food", "sleep", "health", "habits"],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "exp-travel-vacation-shopping",
        "category": "travel",
        "title": "Buying clothes during vacations",
        "situation": "Shopping for new clothes while on holiday",
        "lesson": "Bought several new clothes during vacation, leading to a cramped suitcase on the return flight.",
        "next_time_advice": "Leave 25-30% empty suitcase space when departing so new purchases fit easily.",
        "tags": ["travel", "shopping", "packing", "luggage"],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
    {
        "id": "exp-travel-san-diego",
        "category": "travel",
        "title": "San Diego vacation highlights",
        "situation": "Visited San Diego for vacation",
        "lesson": "Loved the weather, coastal walks, and relaxed atmosphere in San Diego very much.",
        "next_time_advice": "Prioritize coastal stays near Pacific Beach / La Jolla and allocate at least 4-5 days.",
        "tags": ["travel", "destinations", "san-diego", "favorites"],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    },
]

for item in seed_data:
    doc_id = item["id"]
    db.collection(COLLECTION_NAME).document(doc_id).set(item)
    print(f"Seeded document: {doc_id}")

print("Seeding complete!")
