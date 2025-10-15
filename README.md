Be sure to be in the right directory
cd tischtennis-elo

Struktur:
tischtennis-elo
    app.py
    models.py
    test_app.py
    templates
        edit_player.html
        index.html
    venv/


um virtuelle Umgebung zu erstellen
python -m venv venv

hier muss man rein für Flask etc.
venv\Scripts\activate

Flask installieren
pip install flask sqlalchemy
pip install flask_sqlalchemy

kontrollieren obs passt:
pip list (schauen ob flask, sqlalchemy und flask_sqlalchemy drinnen ist)

um die Website zu starten:
flask run

FÜRS TESTEN:
pip install pytest
pytest -v -> damit die Tests durchlaufen.

