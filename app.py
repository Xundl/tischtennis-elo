import re
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
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
    
    from sqlalchemy import func
    
    #Prüfen, ob Name bereits existiert (case-insensitive)
    existing = Player.query.filter(func.lower(Player.name) == name.lower()).first()
    if existing:
        flash("SPIELER EXISTIERT BEREITS!")
        return redirect('/')
    
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
@app.route("/add_game", methods=["POST"])
def add_game():
    p1_name = request.form["p1_name"].strip()
    p2_name = request.form["p2_name"].strip()
    p1_score = int(request.form["p1_score"])
    p2_score = int(request.form["p2_score"])

    p1 = Player.query.filter(func.lower(Player.name) == p1_name.lower()).first()
    p2 = Player.query.filter(func.lower(Player.name) == p2_name.lower()).first()

    if not p1 or not p2:
        flash("Einer der Spieler wurde nicht gefunden.")
        return redirect(url_for("index"))
    if p1.id == p2.id:
        flash("Ein Spieler kann nicht gegen sich selbst spielen.")
        return redirect(url_for("index"))

    # Gewinner/Verlierer bestimmen
    if p1_score > p2_score:
        winner, loser = p1, p2
        winner_score, loser_score = p1_score, p2_score
    elif p2_score > p1_score:
        winner, loser = p2, p1
        winner_score, loser_score = p2_score, p1_score
    else:
        flash("Unentschieden sind nicht erlaubt.")
        return redirect(url_for("index"))

    # Elo aktualisieren
    win_change, lose_change, bonus, winstreak = update_elo(winner, loser, winner_score, loser_score)

    # Spiel speichern
    game = Game(
        p1_id=p1.id,
        p2_id=p2.id,
        p1_score=p1_score,
        p2_score=p2_score,
        p1_change=win_change if winner == p1 else lose_change,
        p2_change=lose_change if winner == p1 else win_change,
        p1_elo_after=p1.elo,
        p2_elo_after=p2.elo,
    )
    db.session.add(game)
    db.session.commit()

    # Flash-Nachricht mit Winstreak Info
    bonus_text = f" (+{bonus} Winstreak: {winstreak} 🔥)" if bonus > 0 else ""
    flash(f"{winner.name} gewinnt! +{win_change}{bonus_text} | {loser.name} verliert {abs(lose_change)} Elo")

    return redirect(url_for("index"))


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

@app.route('/history')
def history():
    games = Game.query.order_by(Game.id.desc()).limit(20).all()
    players = {p.id: p.name for p in Player.query.all()}
    return render_template("history.html", games=games, players=players)

@app.route("/player/<int:player_id>")
def player_profile(player_id):
    player = Player.query.get_or_404(player_id)

    # Alle Spiele mit diesem Spieler
    games = Game.query.filter(
        (Game.p1_id == player.id) | (Game.p2_id == player.id)
    ).order_by(Game.id.desc()).limit(20).all()

    # Win/Loss zählen
    wins = 0
    losses = 0
    for g in games:
        if (g.p1_id == player.id and g.p1_score > g.p2_score) or \
           (g.p2_id == player.id and g.p2_score > g.p1_score):
            wins += 1
        else:
            losses += 1

    total = wins + losses
    winrate = round((wins / total * 100), 1) if total > 0 else 0

    # Rank berechnen
    top1 = player.elo == db.session.query(db.func.max(Player.elo)).scalar()
    rank = player.get_rank(top1=top1)

    # Player-Lookup für Gegnernamen
    players = {p.id: p.name for p in Player.query.all()}

    return render_template(
        "player.html",
        player=player,
        games=games,
        players=players,
        wins=wins,
        losses=losses,
        winrate=winrate,
        rank=rank,
    )


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)