import re
from flask import Flask, render_template, request, redirect, flash
from models import db, Player, Game, update_elo

# Flask-App initialisieren
app = Flask(__name__)

app.secret_key = "supersecret"

# Datenbank konfigurieren (lokale SQLite-Datei)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///elo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Datenbanktabellen erzeugen (falls nicht vorhanden)
with app.app_context():
    db.create_all()

# Startseite: zeigt Spieler & ihre Elo an
@app.route('/')
def index():
    players = Player.query.order_by(Player.elo.desc()).all()
    if players:
        players[0].rank_name = players[0].get_rank(top1=True)
        for p in players[1:]:
            p.rank_name = p.get_rank()
            
    else:
        for p in players:
            p.rank_name = p.get_rank()
                
    return render_template('index.html', players=players)

# Spieler hinzufügen
@app.route('/add_player', methods=['POST'])
def add_player():
    import re
    
    name = request.form['name'].strip()
    custom_elo = request.form.get("elo", "").strip()
    admin_pw = request.form.get("admin_password", "").strip()
    
    if not re.match(r'^[A-Za-z0-9äöüÄÖÜß\s]+$', name):
        flash("UNGÜLTIGER NAME: Nur Buchstaben, Zahlen und Leerzeichen erlaubt")
        return redirect('/')
    
    #Prüfen, ob Name bereits existiert
    if Player.query.filter_by(name=name).first():
        flash("SPIELER EXISTIERT BEREITS!")
        return redirect ('/')
    
    elo_value = 300
    
    if custom_elo:
        try:
            elo_value = float(custom_elo)
        except ValueError:
            flash("UNGUELTIGER ELO-WERT!")
            return redirect("/")
        
        if elo_value < 100 or elo_value > 1000:
            flash("Elo muss zwischen 100 und 1000 liegen!")
            return redirect("/")
        
        ADMIN_PASSWORD = "123"
        if admin_pw != ADMIN_PASSWORD:
            flash("FALSCHES PASSWORT! Spieler NICHT erstellt.")
            return redirect("/")
    
    new_player = Player(name=name, elo=elo_value)
    db.session.add(new_player)
    db.session.commit()
    
    flash(f"✅ Spieler '{name}' wurde hinzugefügt")
    return redirect('/')

# Spiel hinzufügen
@app.route('/add_game', methods=['POST'])
def add_game():
    p1_name = request.form['p1_name']
    p2_name = request.form['p2_name']
    p1_score = int(request.form['p1_score'])
    p2_score = int(request.form['p2_score'])

    p1 = Player.query.filter_by(name=p1_name).first()
    p2 = Player.query.filter_by(name=p2_name).first()

    if not p1 or not p2:
        return "❌ Spieler nicht gefunden!"

    # Gewinner/Verlierer bestimmen
    winner, loser = (p1, p2) if p1_score > p2_score else (p2, p1)
    update_elo(winner, loser, winner_score=p1_score if winner == p1 else p2_score, loser_score=p2_score if winner == p1 else p1_score)

    # Spiel speichern
    game = Game(p1_id=p1.id, p2_id=p2.id, p1_score=p1_score, p2_score=p2_score)
    db.session.add(game)
    db.session.commit()

    return redirect('/')

# Vollständiges Leaderboard anzeigen
@app.route('/leaderboard')
def leaderboard():
    players = Player.query.order_by(Player.elo.desc()).all()
    if players:
        players[0].rank_name = players[0].get_rank(top1=True)
        for p in players[1:]:
            p.rank_name = p.get_rank()
    else:
        for p in players:
            p.rank_name = p.get_rank()

    return render_template('leaderboard.html', players=players)


@app.route("/edit_player/<int:player_id>", methods=["GET", "POST"])
def edit_player(player_id):
    ADMIN_PASSWORD = "123"
    player = Player.query.get_or_404(player_id)

    if request.method == "POST":
        # Passwort prüfen
        entered_pw = request.form.get("admin_password", "").strip()
        if entered_pw != ADMIN_PASSWORD:
            flash("🚫 Falsches Admin-Passwort – Änderung abgebrochen!")
            return redirect("/")

        # Name ändern
        new_name = request.form.get("name", "").strip()
        if not new_name:
            flash("⚠️ Name darf nicht leer sein!")
            return redirect("/")

        # Elo ändern
        try:
            new_elo = float(request.form.get("elo", player.elo))
        except ValueError:
            flash("⚠️ Ungültiger Elo-Wert!")
            return redirect("/")

        if new_elo < 100 or new_elo > 1000:
            flash("⚠️ Elo muss zwischen 100 und 1000 liegen!")
            return redirect("/")

        # Änderungen speichern
        player.name = new_name
        player.elo = new_elo
        db.session.commit()
        flash(f"✅ Spieler '{player.name}' wurde erfolgreich aktualisiert (Elo: {new_elo})")
        return redirect("/")

    # GET: Bearbeitungsformular anzeigen
    return render_template("edit_player.html", player=player)

@app.route("/delete_player/<int:player_id>", methods=["POST"])
def delete_player(player_id):
    ADMIN_PASSWORD = "123"
    player = Player.query.get_or_404(player_id)

    if request.method == "POST":

    # Passwort prüfen
        entered_pw = request.form.get("admin_password", "").strip()
        if entered_pw != ADMIN_PASSWORD:
            flash("🚫 Falsches Admin-Passwort – Spieler wurde NICHT gelöscht.")
            return redirect(f"/edit_player/{player_id}")

    # Spieler wirklich löschen
    db.session.delete(player)
    db.session.commit()
    flash(f"🗑️ Spieler '{player.name}' wurde gelöscht.")
    return redirect("/")

if __name__ == '__main__':
    app.run(debug=True)