#!/usr/bin/env python3
"""
Usage:
  python agent/main.py               # live run (writes to Google Calendar)
  python agent/main.py --dry-run     # test — no calendar writes
  python agent/main.py --keywords "imbalanced,tabular,oversampling"
"""
import argparse
import logging
import os
from datetime import datetime

# ── Logging — file + console ──────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
log_file = f"logs/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

from agent.agent import run_agent
from agent.config import MAX_ITERATIONS

# ── PhD thesis configuration ──────────────────────────────────────────────────
THESIS_KEYWORDS = [
    "imbalanced learning", "class imbalance", "oversampling", "SMOTE",
    "tabular data", "mixed-type data", "synthetic data generation",
    "categorical embeddings", "generative models tabular",
    "fraud detection machine learning",
    "medical diagnosis imbalanced", "cybersecurity anomaly detection",
    "data augmentation imbalanced classification",
]

THESIS_ABSTRACT = (
    "This thesis proposes novel AI approaches to address class imbalance in "
    "machine learning, focusing on mixed-type tabular data with continuous and "
    "categorical features. Applications span fraud detection, medical diagnosis, "
    "and cybersecurity anomaly detection."
)

# User email for authentication
USER_EMAIL = "yousseftajani1@gmail.com"

def main():
    parser = argparse.ArgumentParser(description="PhD Conference Finder Agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Find conferences but skip calendar writes")
    parser.add_argument("--keywords", type=str,
                        help="Comma-separated keywords (overrides THESIS_KEYWORDS)")
    args = parser.parse_args()

    keywords = (
        [k.strip() for k in args.keywords.split(",")]
        if args.keywords else THESIS_KEYWORDS
    )

    logger.info("=" * 60)
    logger.info("PhD Conference Finder Agent")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info(f"Keywords ({len(keywords)}): {', '.join(keywords[:4])}...")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 60)

    result = run_agent(keywords, THESIS_ABSTRACT, dry_run=args.dry_run)

    logger.info("\n" + "=" * 60)
    logger.info(f"Conferences added:    {result.conferences_added}")
    logger.info(f"Candidates evaluated: {result.total_candidates_evaluated}")
    logger.info(f"Dedup skipped:        {result.conferences_skipped_dedup}")
    logger.info(f"Iterations used:      {result.iterations_used}/{MAX_ITERATIONS}")
    logger.info(f"Estimated cost:       ${result.estimated_cost_usd}")
    if result.top_conferences:
        logger.info("\nTop 5 by relevance:")
        for c in result.top_conferences:
            logger.info(f"  [{c.relevance_score}/10] {c.acronym} {c.year} "
                        f"deadline={c.full_paper_deadline} {c.url}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
