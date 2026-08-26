# migrate.py
from app import app
from models import db
with app.app_context():
    db.create_all()
    # Neue Spalten zur bestehenden DB hinzufügen
    with db.engine.connect() as con:
        for col in ['winstreak_1', 'winstreak_3', 'winstreak_5', 'winstreak_7']:
            try:
                con.execute(db.text(f'ALTER TABLE player ADD COLUMN {col} INTEGER DEFAULT 0'))
                con.commit()
            except Exception:
                pass  # Spalte existiert bereits
        print("✅ Migration abgeschlossen")