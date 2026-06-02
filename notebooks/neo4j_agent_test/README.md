# Test suite par défaut
python notebooks/neo4j_agent_test/neo4j_agent_test.py

# Question simple
python notebooks/neo4j_agent_test/neo4j_agent_test.py "How many nodes are there?"

# Avec contexte JSON
python notebooks/neo4j_agent_test/neo4j_agent_test.py --question "List regions" --context '{"filter": "France"}'

# Sortie JSON (pour scripting)
python notebooks/neo4j_agent_test/neo4j_agent_test.py "Show me nodes" --json

# Mode interactif
python notebooks/neo4j_agent_test/neo4j_agent_test.py --interactive

# Surcharge du modèle
python notebooks/neo4j_agent_test/neo4j_agent_test.py --model-provider ollama --model-name llama3.2 "List all nodes"