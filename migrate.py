from app import app
from models import db
from datetime import date

with app.app_context():
    db.create_all()

    with db.engine.connect() as con:
        for col, typ in [
            ('inactive_counter', 'INTEGER DEFAULT 0'),
            ('is_inactive', 'BOOLEAN DEFAULT 0'),
            ('last_active_date', 'DATE'),
        ]:
            try:
                con.execute(db.text(f'ALTER TABLE player ADD COLUMN {col} {typ}'))
                con.commit()
                print(f"✅ {col} hinzugefügt")
            except Exception:
                print(f"ℹ️  {col} existiert bereits")

        # last_active_date für bestehende Spieler auf heute setzen
        try:
            con.execute(db.text(f"UPDATE player SET last_active_date = '{date.today()}' WHERE last_active_date IS NULL"))
            con.commit()
            print("✅ last_active_date für bestehende Spieler gesetzt")
        except Exception as e:
            print(f"⚠️ {e}")

    print("✅ Migration abgeschlossen")