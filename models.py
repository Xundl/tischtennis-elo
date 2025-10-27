from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    elo = db.Column(db.Float, default=300)
    winstreak = db.Column(db.Integer, default=0)

    def get_rank(self, top1=False):
        if top1:
            return "Karl Jindraks Doppelpartner"
        
        elo = max(min(self.elo, 1000), 100)
        tiers = [
            (100, 249, "Papier"),
            (250, 399, "Plastik"),
            (400, 549, "Holz"),
            (550, 699, "Metall"),
            (700, 849, "Pfarrer"),
            (850, 1000, "Familie Yarak"),
        ]
        
        for low, high, name in tiers:
            if low <= elo <= high:
                divisions = 3
                step = (high - low) / divisions
                if elo < low + step:
                    div = 3
                elif elo < low + 2 * step:
                    div = 2
                else:
                    div = 1
                return f"{name} {div}"
        return "Unranked"

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    p1_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    p2_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    p1_score = db.Column(db.Integer)
    p2_score = db.Column(db.Integer)
    p1_change = db.Column(db.Float)
    p2_change = db.Column(db.Float)
    p1_elo_after = db.Column(db.Float)
    p2_elo_after = db.Column(db.Float)

def update_elo(winner, loser, winner_score=None, loser_score=None, k=32):
    # Erwartungswert des Gewinners
    expected_win = 1 / (1 + 10 ** ((loser.elo - winner.elo) / 400))

    # Punktedifferenz-Faktor (leicht höhere Belohnung bei klaren Siegen)
    if winner_score is not None and loser_score is not None:
        diff = abs(winner_score - loser_score)
        diff_factor = 1 + (min(diff, 10) / 20)
    else:
        diff_factor = 1.0

    # Grund-Delta
    delta = k * (1 - expected_win) * diff_factor
    delta = int(round(delta))

    # 🔥 Winstreak-Bonus: ab 3 Siegen in Folge +5 Punkte
    bonus = 5 if winner.winstreak >= 2 else 0  # also ab 3. Sieg
    delta_with_bonus = delta + bonus

    # Gewinner bekommt vollen Gewinn
    winner_new_elo = winner.elo + delta_with_bonus

    # Verlierer verliert nur 75 %
    loser_delta = int(round(delta * 0.75))
    loser_new_elo = loser.elo - loser_delta

    # Elo-Caps
    winner.elo = min(1000, winner_new_elo)
    loser.elo = max(100, loser_new_elo)

    # 🔁 Winstreak aktualisieren
    winner.winstreak += 1
    loser.winstreak = 0

    db.session.commit()

    # Rückgabe: Änderungen + Bonus-Info
    return delta_with_bonus, -loser_delta, bonus, winner.winstreak