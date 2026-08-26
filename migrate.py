from app import app
from models import db

with app.app_context():
    db.create_all()  # Erstellt Season, SeasonSnapshot falls nicht vorhanden

    with db.engine.connect() as con:
        # placements_played zu bestehenden Spielern hinzufügen
        # DEFAULT 3 damit bestehende Spieler nicht nochmal Placements machen müssen
        try:
            con.execute(db.text('ALTER TABLE player ADD COLUMN placements_played INTEGER DEFAULT 3'))
            con.commit()
            print("✅ placements_played Spalte hinzugefügt")
        except Exception:
            print("ℹ️  placements_played existiert bereits")

    print("✅ Migration abgeschlossen – Season & Snapshot Tabellen erstellt")