"""
PALIMPSEST Database Seeder
Populates initial sample projects, conversations, messages, memories, and benchmarks
for out-of-the-box demonstration.
"""

from models import db, Project, Conversation, Message, utc_now, generate_uuid
from services import VersionControlService, MemoryClassifier


def seed_database():
    """Seeds the database if empty."""
    if Project.query.first():
        return  # Database already seeded

    # 1. Create Sample Project 1: Healthcare Backend
    p1 = Project(
        id=generate_uuid(),
        name="Healthcare EHR Core API",
        description="High-security medical records service with strict HIPAA data-handling requirements.",
        objective="Build a HIPAA-compliant medical records API with PostgreSQL and JWT auth.",
        token_budget=2048,
    )
    db.session.add(p1)
    db.session.commit()

    b1 = VersionControlService.get_or_create_default_branch(p1.id)

    # Add conversation
    c1 = Conversation(
        id=generate_uuid(),
        project_id=p1.id,
        title="Architecture & Compliance Kickoff",
    )
    db.session.add(c1)
    db.session.commit()

    sample_messages = [
        ("user", "Our team is initiating development of the Healthcare EHR Core API."),
        ("user", "Mandatory database requirement: We must use PostgreSQL with async SQLAlchemy."),
        ("user", "Security constraint: Authentication must strictly use signed JWT tokens with 15-minute expirations."),
        ("user", "Compliance constraint: The entire system must strictly comply with HIPAA regulations. Plaintext PHI in logs or public storage is strictly forbidden."),
        ("assistant", "Understood. PostgreSQL, async SQLAlchemy, JWT authentication, and strict HIPAA compliance are locked in."),
        ("user", "Hello there! Good morning. Hope the sprint planning went well."),
        ("user", "Can you explain what the capital of Iceland is? Just curious."),
        ("user", "Also, the test coverage requirement is non-negotiable: minimum 90% unit test coverage required prior to staging deployment."),
    ]

    for role, text in sample_messages:
        msg = Message(
            id=generate_uuid(),
            conversation_id=c1.id,
            role=role,
            content=text,
            token_count=len(text.split()) * 2,
            is_processed=False,
        )
        db.session.add(msg)
    db.session.commit()

    # 2. Create Sample Project 2: E-Commerce Analytics Engine
    p2 = Project(
        id=generate_uuid(),
        name="E-Commerce Stream Analytics",
        description="Real-time event processing for e-commerce checkout and fraud detection.",
        objective="Process event streams using Redis streams and FastAPI within 1500 tokens.",
        token_budget=1500,
    )
    db.session.add(p2)
    db.session.commit()
    VersionControlService.get_or_create_default_branch(p2.id)

    c2 = Conversation(
        id=generate_uuid(),
        project_id=p2.id,
        title="Ingestion Pipeline Design",
    )
    db.session.add(c2)
    db.session.commit()

    sample_messages_2 = [
        ("user", "Stream processing requirement: Must use Redis Streams for ingestion buffer."),
        ("user", "Throughput SLA: Must sustain 10,000 events per second with sub-50ms latency."),
        ("user", "Great job team! Thanks for the coffee."),
    ]
    for role, text in sample_messages_2:
        msg = Message(
            id=generate_uuid(),
            conversation_id=c2.id,
            role=role,
            content=text,
            token_count=len(text.split()) * 2,
            is_processed=False,
        )
        db.session.add(msg)
    db.session.commit()
