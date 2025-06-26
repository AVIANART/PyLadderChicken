class TwitchClient:
    def __init__(self, token: str):
        self.token = token

    async def check_for_race_vos(self, race_id: str, player_id: str):
        # Simulate checking for VODs
        print(f"Checking for VODs for {race_id} and player {player_id}")
