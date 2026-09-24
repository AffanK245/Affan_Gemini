import os
from google.cloud import firestore

FIRESTORE_PROJECT = "qwiklabs-gcp-02-68959e46a2d9"

db = firestore.Client(project=FIRESTORE_PROJECT)

sample_destinations = [
    {
        "id": "tokyo-japan",
        "name": "Tokyo",
        "country": "Japan",
        "category": "Urban & Culture",
        "avg_cost_usd": 180,
        "description": "Vibrant capital combining ultramodern skyscrapers with historic temples and world-class cuisine.",
        "popular_spots": ["Shinjuku", "Shibuya Crossing", "Senso-ji Temple", "Akihabara"],
    },
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "category": "Culture & Heritage",
        "avg_cost_usd": 150,
        "description": "Famous for classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses.",
        "popular_spots": ["Fushimi Inari Taisha", "Arashiyama Bamboo Grove", "Kinkaku-ji"],
    },
    {
        "id": "paris-france",
        "name": "Paris",
        "country": "France",
        "category": "Art & Culture",
        "avg_cost_usd": 220,
        "description": "France's capital and a global center for art, fashion, gastronomy, and culture.",
        "popular_spots": ["Eiffel Tower", "Louvre Museum", "Notre-Dame Cathedral"],
    },
    {
        "id": "bali-indonesia",
        "name": "Bali",
        "country": "Indonesia",
        "category": "Beach & Wellness",
        "avg_cost_usd": 80,
        "description": "Indonesian island known for iconic rice paddies, beaches, coral reefs, and volcanic mountains.",
        "popular_spots": ["Ubud Rice Terraces", "Uluwatu Temple", "Canggu Beach"],
    },
    {
        "id": "rome-italy",
        "name": "Rome",
        "country": "Italy",
        "category": "History & Heritage",
        "avg_cost_usd": 160,
        "description": "Sprawling cosmopolitan city with nearly 3,000 years of globally influential art and architecture.",
        "popular_spots": ["Colosseum", "Vatican City", "Trevi Fountain"],
    },
]


def seed():
    print(f"Seeding Firestore collection 'destinations' in project '{FIRESTORE_PROJECT}'...")
    collection_ref = db.collection("destinations")
    for dest in sample_destinations:
        doc_id = dest["id"]
        collection_ref.document(doc_id).set(dest)
        print(f"  ✓ Saved destination: {dest['name']} ({doc_id})")
    print("Seeding complete!")


if __name__ == "__main__":
    seed()
