import os
import json
import google.generativeai as genai
from utils.config import is_gemini_active, GEMINI_MODEL
from reasoning.prompts import HYPOTHESIS_PROMPT

def get_mock_hypotheses() -> dict:
    return {
      "hypotheses": [
        {
          "title": "Database connection pool leak in payment-api version v1.4.2",
          "description": "The deployment DEP-772 at 10:00:00Z introduced payment-api v1.4.2. A suspected connection leak exists where database connections are not properly released back to the pool, saturating the PostgreSQL maximum connection limit (200) by 10:08:00Z.",
          "confidence": 0.92,
          "evidence_for": [
            "payment-api v1.4.2 deployed at 10:00:00Z",
            "db_connections metric starts rising immediately after, peaking at 200 at 10:08:00Z",
            "Log messages warn of connection pool utilization at 85% and 95% shortly after deploy",
            "SQLExceptions show cannot acquire connection from pool",
            "Matches past incident INC-001 where auth-service had a redis connection leak"
          ],
          "evidence_against": [
            "Other database services (e.g. auth-service) are not throwing connection pool warnings, suggesting the DB itself is healthy but the payment-api pool is exhausted."
          ]
        },
        {
          "title": "Sudden checkout traffic spike flooding payment service",
          "description": "A high volume of concurrent checkout requests overwhelmed the payment-api, exhausting all available database connection pool slots.",
          "confidence": 0.35,
          "evidence_for": [
            "High HTTP 5xx rates and user complaints about slow payments started around 10:11:00Z",
            "Database CPU utilization reached high levels (50.1%) under load"
          ],
          "evidence_against": [
            "Metrics do not show a corresponding spike in request throughput; rather, latency rose first, which is indicative of blocking behavior rather than external load spike.",
            "Normal traffic does not justify exhaustion of 200 connection threads in 8 minutes."
          ]
        },
        {
          "title": "PostgreSQL database server lock/hang",
          "description": "The core database instance db-primary-01.internal is hung or has locked tables, preventing payment-api from finishing queries and holding connections open.",
          "confidence": 0.20,
          "evidence_for": [
            "Log shows PostgreSQL warning: Client connection limit reached",
            "User tickets complain that loading spinner spins forever (queries hung)"
          ],
          "evidence_against": [
            "Auth-service is still functioning normally without DB timeout warnings, meaning PostgreSQL is still responding, just refusing new connections due to maxing out."
          ]
        }
      ]
    }

def analyze_hypotheses(timeline_str: str, past_incidents_str: str) -> dict:
    if is_gemini_active():
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel(GEMINI_MODEL)
            prompt = HYPOTHESIS_PROMPT.format(
                timeline=timeline_str,
                past_incidents=past_incidents_str
            )
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            # Remove potential code blocks formatting
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
                
            return json.loads(text.strip())
        except Exception as e:
            print(f"Error calling Gemini: {e}. Falling back to mock hypotheses.")
            
    return get_mock_hypotheses()
