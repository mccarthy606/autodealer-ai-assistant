#!/bin/bash
# Ejemplos de curl para AI Inventory Assistant
# Base URL (ajustar si corresponde)
BASE=http://localhost:8000

echo "=== 1. Health ==="
curl -s "$BASE/health" | jq .

echo -e "\n=== 2. Crear concesionario ==="
curl -s -X POST "$BASE/admin/dealerships" \
  -H "Content-Type: application/json" \
  -d '{"name": "AutoShop Argentina", "address": "Av. Libertador 1234, CABA", "phone": "+54911..."}' | jq .

echo -e "\n=== 3. Importar CSV ==="
curl -s -X POST "$BASE/import/csv" \
  -F "file=@sample_inventory.csv" | jq .

echo -e "\n=== 4. Webhook WhatsApp (JSON genérico) ==="
curl -s -X POST "$BASE/webhooks/whatsapp" \
  -H "Content-Type: application/json" \
  -d '{"user_phone": "+5491112345678", "message_text": "Tienen Hilux 0 km?"}' | jq .

echo -e "\n=== 5. Webhook WhatsApp (formato Twilio) ==="
curl -s -X POST "$BASE/webhooks/whatsapp" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=+5491112345678&Body=Cuanto cuesta la Ranger?" | jq .

echo -e "\n=== 6. Listar inventario ==="
curl -s "$BASE/admin/inventory" | jq .

echo -e "\n=== 7. Listar leads ==="
curl -s "$BASE/admin/leads" | jq .

echo -e "\n=== 8. Métricas ==="
curl -s "$BASE/admin/metrics" | jq .
