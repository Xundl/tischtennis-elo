import pytest
from app import app, db, Player, Game, update_elo
from flask import url_for

@pytest.fixture(autouse=True)
def setup_database():
    """Vor jedem Test eine frische In-Memory-Datenbank erstellen"""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()

def add_player(name, elo=500):
    """Hilfsfunktion: Spieler anlegen"""
    player = Player(name=name, elo=elo)
    db.session.add(player)
    db.session.commit()
    return player

# ----------------------------------------------------------
# 1️⃣ Spieler anlegen in der Datenbank passt
# ----------------------------------------------------------
def test_add_player_to_db():
    with app.app_context():
        player = add_player("Jonas")
        fetched = Player.query.filter_by(name="Jonas").first()
        assert fetched is not None
        assert fetched.name == "Jonas"
        assert fetched.elo == 500

# ----------------------------------------------------------
# 2️⃣ Gewinner bekommt Punkte, Verlierer verliert Punkte
# ----------------------------------------------------------
def test_winner_gets_points_loser_loses():
    with app.app_context():
        p1 = add_player("A", 500)
        p2 = add_player("B", 500)
        update_elo(p1, p2)
        assert p1.elo > 500
        assert p2.elo < 500

# ----------------------------------------------------------
# 3️⃣ Punkteabstand beeinflusst Änderung (11:2 > 11:9)
# ----------------------------------------------------------
def test_score_difference_affects_elo():
    with app.app_context():
        p1 = add_player("A", 500)
        p2 = add_player("B", 500)

        # Erstes Spiel: 11:9 (kleiner Unterschied)
        elo_before = p1.elo
        update_elo(winner=p1, loser=p2, winner_score=11, loser_score=9)
        elo_after_small_diff = p1.elo - elo_before

        # Elo zurücksetzen für fairen Vergleich
        p1.elo, p2.elo = 500, 500
        db.session.commit()

        # Zweites Spiel: 11:2 (großer Unterschied)
        elo_before = p1.elo
        update_elo(winner=p1, loser=p2, winner_score=11, loser_score=2)
        elo_after_large_diff = p1.elo - elo_before

        print(f"Elo Gewinn (11:9): {elo_after_small_diff:.2f}")
        print(f"Elo Gewinn (11:2): {elo_after_large_diff:.2f}")

        assert elo_after_large_diff > elo_after_small_diff, \
            f"Bei größerem Punktunterschied sollte der Elo-Gewinn höher sein ({elo_after_large_diff:.2f} vs. {elo_after_small_diff:.2f})"

# ----------------------------------------------------------
# 4️⃣ Elo bleibt gespeichert
# ----------------------------------------------------------
def test_elo_persistence():
    with app.app_context():
        p1 = add_player("A", 500)
        p2 = add_player("B", 500)
        update_elo(p1, p2)
        elo_after = p1.elo

        # Reload from DB
        p1_fetched = Player.query.filter_by(name="A").first()
        assert abs(p1_fetched.elo - elo_after) < 0.0001

# ----------------------------------------------------------
# 5️⃣ Elo-Differenzen werden berücksichtigt
# ----------------------------------------------------------
def test_elo_difference_impact():
    with app.app_context():
        strong = add_player("Strong", 800)
        weak = add_player("Weak", 400)
        mid = add_player("Mid", 700)

        # Fall 1: Strong verliert gegen Weak
        update_elo(weak, strong)
        diff_loss_vs_weak = 800 - strong.elo

        # Reset Werte
        strong.elo, mid.elo = 800, 700
        db.session.commit()

        # Fall 2: Strong verliert gegen Mid
        update_elo(mid, strong)
        diff_loss_vs_mid = 800 - strong.elo

        # Verlust gegen viel schwächeren Gegner sollte größer sein
        assert diff_loss_vs_weak > diff_loss_vs_mid

# ----------------------------------------------------------
# 6️⃣ Doppelte Namen
# ----------------------------------------------------------
def test_duplicate_names():
    with app.app_context():
        add_player("Jonas")
        with pytest.raises(Exception):
            add_player("Jonas")  # sollte Exception werfen wegen unique=True
# ----------------------------------------------------------
# 7️⃣ Spielernamen-Validierung: keine Sonderzeichen
# ----------------------------------------------------------
def test_invalid_player_name_rejected():
    with app.test_client() as client, app.app_context():
        invalid_names = ["!Jonas", "Paul@", "Tim#", "Anna$"]
        for name in invalid_names:
            response = client.post("/add_player", data={"name": name}, follow_redirects=True)
            data = response.get_data(as_text=True).upper()
            assert "UNGÜLTIGER NAME" in data
            assert Player.query.filter_by(name=name).first() is None

# ----------------------------------------------------------
# 8️⃣ Doppelte Namen werden abgefangen
# ----------------------------------------------------------
def test_duplicate_name_rejected():
    with app.test_client() as client, app.app_context():
        db.session.add(Player(name="Lukas"))
        db.session.commit()
        response = client.post("/add_player", data={"name": "Lukas"}, follow_redirects=True)
        data = response.get_data(as_text=True).upper()
        assert "SPIELER EXISTIERT BEREITS" in data
        assert Player.query.filter_by(name="Lukas").count() == 1

# ----------------------------------------------------------
# 9️⃣ Alphabetische Sortierung der Spieler
# ----------------------------------------------------------
def test_players_sorted_alphabetically():
    with app.app_context():
        names = ["Zoe", "Anna", "Paul", "Ben"]
        for n in names:
            db.session.add(Player(name=n))
        db.session.commit()

        # Sortiert im Python-Backend (wie im Template)
        players_sorted = Player.query.order_by(Player.name.asc()).all()
        names_sorted = [p.name for p in players_sorted]
        assert names_sorted == sorted(names)

# ----------------------------------------------------------
# 🔟 Autocomplete enthält alle Spielernamen
# ----------------------------------------------------------
def test_datalist_contains_all_players():
    with app.test_client() as client, app.app_context():
        # Spieler anlegen
        db.session.add_all([Player(name="Tom"), Player(name="Max"), Player(name="Elias")])
        db.session.commit()

        response = client.get("/")
        data = response.data.decode("utf-8")

        # Prüfen, ob alle Spieler als <option> im HTML stehen
        for n in ["Tom", "Max", "Elias"]:
            assert f'<option value="{n}">' in data
            
# ----------------------------------------------------------
# 11️⃣ Extremfälle: Elo darf nie <100 oder >1000 werden
# ----------------------------------------------------------
def test_elo_limits():
    with app.app_context():
        low = add_player("Low", 120)
        high = add_player("High", 980)

        # High verliert mehrfach → Elo sollte nicht <100 gehen
        for _ in range(20):
            update_elo(low, high)
        db.session.refresh(high)
        assert high.elo >= 100

        # Low gewinnt mehrfach → Elo sollte nicht >1000 gehen
        for _ in range(20):
            update_elo(low, high)
        db.session.refresh(low)
        assert low.elo <= 1000


# ----------------------------------------------------------
# 12️⃣ Spiel korrekt in Datenbank gespeichert
# ----------------------------------------------------------
def test_game_saved_correctly():
    with app.app_context():
        p1 = add_player("Anna")
        p2 = add_player("Berta")

        game = Game(p1_id=p1.id, p2_id=p2.id, p1_score=11, p2_score=8)
        db.session.add(game)
        db.session.commit()

        result = Game.query.first()
        assert result.p1_score == 11
        assert result.p2_score == 8
        assert result.p1_id == p1.id
        assert result.p2_id == p2.id


# ----------------------------------------------------------
# 13️⃣ Routing: Homepage und Add-Routen erreichbar
# ----------------------------------------------------------
def test_routes_reachable():
    with app.test_client() as client:
        res_index = client.get("/")
        assert res_index.status_code == 200

        # Formulare dürfen per POST erreichbar sein
        res_add_player = client.post("/add_player", data={"name": "Max"}, follow_redirects=True)
        assert res_add_player.status_code == 200

        res_add_game = client.post(
            "/add_game",
            data={"p1_name": "Max", "p2_name": "Unknown", "p1_score": 11, "p2_score": 9},
            follow_redirects=True
        )
        # Sollte Fehlermeldung liefern, da Spieler "Unknown" nicht existiert
        assert "Spieler nicht gefunden" in res_add_game.get_data(as_text=True)


# ----------------------------------------------------------
# 14️⃣ Spieler hinzufügen funktioniert (korrekt)
# ----------------------------------------------------------
def test_add_player_via_post():
    with app.test_client() as client, app.app_context():
        response = client.post("/add_player", data={"name": "Tom"}, follow_redirects=True)
        assert response.status_code == 200
        assert Player.query.filter_by(name="Tom").first() is not None


# ----------------------------------------------------------
# 15️⃣ Spiel mit nicht existierenden Spielern → Fehlermeldung
# ----------------------------------------------------------
def test_game_with_nonexistent_players():
    with app.test_client() as client, app.app_context():
        db.session.add_all([Player(name="A"), Player(name="B")])
        db.session.commit()

        response = client.post(
            "/add_game",
            data={"p1_name": "X", "p2_name": "Y", "p1_score": 11, "p2_score": 9},
            follow_redirects=True
        )
        data = response.get_data(as_text=True)
        assert "Spieler nicht gefunden" in data


# ----------------------------------------------------------
# 16️⃣ Leaderboard richtig sortiert nach Elo
# ----------------------------------------------------------
def test_leaderboard_sorted_correctly():
    with app.app_context():
        a = add_player("A", 300)
        b = add_player("B", 700)
        c = add_player("C", 500)

        players = Player.query.order_by(Player.elo.desc()).all()
        elo_order = [p.elo for p in players]
        assert elo_order == sorted(elo_order, reverse=True)
# ----------------------------------------------------------
# 18️⃣ Top-1-Spieler hat den Titel "Karl Jindraks Doppelpartner"
# ----------------------------------------------------------
def test_top_player_has_special_rank():
    with app.app_context():
        # Drei Spieler mit unterschiedlichen Elos
        add_player("Karl", 950)
        add_player("Jonas", 600)
        add_player("Timo", 400)

        players = Player.query.order_by(Player.elo.desc()).all()
        players[0].rank_name = players[0].get_rank(top1=True)
        for p in players[1:]:
            p.rank_name = p.get_rank()

        # Top-1
        assert players[0].rank_name == "Karl Jindraks Doppelpartner"
        # Andere haben normale Ränge
        assert "Metall" in players[1].rank_name or "Holz" in players[1].rank_name


# ----------------------------------------------------------
# 19️⃣ Ranknamen passen zu Elos (Kategorientest)
# ----------------------------------------------------------
def test_correct_rank_names_for_elos():
    with app.app_context():
        cases = [
            (120, "Papier"),
            (300, "Plastik"),
            (500, "Holz"),
            (600, "Metall"),
            (720, "Pfarrer"),
            (900, "Familie Yarak"),
        ]
        for elo, expected_tier in cases:
            p = add_player(f"P{elo}", elo)
            rank = p.get_rank()
            assert expected_tier in rank, f"Elo {elo} sollte {expected_tier} sein, bekam {rank}"


# ----------------------------------------------------------
# 20️⃣ Grenzfall Elo = 550 → sollte Metall sein (obere Grenze zählt)
# ----------------------------------------------------------
def test_rank_boundary_at_550():
    with app.app_context():
        p = add_player("Grenzfall", 550)
        rank = p.get_rank()
        assert "Metall" in rank, f"Elo 550 sollte Metall sein, bekam {rank}"


# ----------------------------------------------------------
# 21️⃣ Divisions funktionieren korrekt (z. B. 300 Elo = Plastik 2)
# ----------------------------------------------------------
def test_division_assignment():
    with app.app_context():
        p = add_player("Division", 300)
        rank = p.get_rank()
        assert rank == "Plastik 2", f"300 Elo sollte Plastik 2 sein, bekam {rank}"


# ----------------------------------------------------------
# 22️⃣ Rank aktualisiert sich nach Elo-Änderung (z. B. durch Sieg)
# ----------------------------------------------------------
def test_rank_updates_after_game():
    with app.app_context():
        p1 = add_player("Player1", 280)  # Plastik 3
        p2 = add_player("Player2", 500)  # Holz 2
        old_rank = p1.get_rank()
        update_elo(p1, p2)  # p1 gewinnt gegen stärkeren Gegner → Elo steigt
        db.session.refresh(p1)
        new_rank = p1.get_rank()
        assert old_rank != new_rank, f"Rank sollte sich ändern, blieb aber {old_rank}"
        assert "Plastik" in old_rank and new_rank != old_rank


# ----------------------------------------------------------
# 23️⃣ Rank-Division aktualisiert sich nach Elo-Änderung
# ----------------------------------------------------------
def test_division_changes_after_elo_update():
    with app.app_context():
        p1 = add_player("DivPlayer", 260)  # Plastik 3
        p2 = add_player("Opponent", 400)   # Holz 3
        old_rank = p1.get_rank()
        # Lass p1 einige Male gewinnen, um Elo zu steigern
        for _ in range(5):
            update_elo(p1, p2)
        db.session.refresh(p1)
        new_rank = p1.get_rank()
        # Sollte immer noch "Plastik", aber höhere Division (2 oder 1)
        assert "Plastik" in new_rank
        assert new_rank != old_rank
