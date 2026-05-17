from qdrant_client import QdrantClient

qdrant_client = QdrantClient(
    url="https://9245ab69-033b-401f-9ef6-07ec4d1f1bce.eu-central-1-0.aws.cloud.qdrant.io:6333", 
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6MzA1MmE5MDQtMzUyYy00ODc3LTg3ZWMtNjg3OGU3NWU1MGUyIn0.rmYjnyVHtWvbu6CMpD9cLnpL1aaoTe0sIhk-vRQJV5A",
)

print(qdrant_client.get_collections())