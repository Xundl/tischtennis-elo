from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    elo = db.Column(db.Float, default=300)

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

# ELO Berechnung (klassisch nach ELO-Formel)
# ELO Berechnung (mit Berücksichtigung des Punkteunterschieds)
def update_elo(winner, loser, winner_score=None, loser_score=None, k=32):
    # Erwartungswert basierend auf Elo
    expected_win = 1 / (1 + 10 ** ((loser.elo - winner.elo) / 400))

    # Falls Scores übergeben wurden → Punkteabstand in Faktor umwandeln (0.5–1.5)
    if winner_score is not None and loser_score is not None:
        diff = abs(winner_score - loser_score)
        # Faktor skaliert den K-Wert leicht, aber bleibt fair
        # z.B. bei 11:9 (diff=2) → 1.0, bei 11:1 (diff=10) → ca. 1.4
        diff_factor = 1 + (min(diff, 10) / 20)  # max +50 % Wirkung
    else:
        diff_factor = 1.0

    # Neue Elo-Werte berechnen
    delta = k * (1 - expected_win) * diff_factor
    winner.elo += delta
    loser.elo -= delta

    # Werte begrenzen
    winner.elo = min(max(winner.elo, 100), 1000)
    loser.elo = min(max(loser.elo, 100), 1000)

    db.session.commit()
