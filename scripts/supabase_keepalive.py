import os
import sys
from supabase import create_client, Client


def main() -> None:
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print(
            "BŁĄD: Brak wymaganych zmiennych środowiskowych SUPABASE_URL lub SUPABASE_KEY.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        # Lekkie zapytanie pobierające maksymalnie 1 wiersz z tabeli user_data
        response = supabase.table("user_data").select("user_email").limit(1).execute()
        print(
            f"Keep-alive zakończony sukcesem! Baza odpowiedziała poprawnie (pobrano wierszy: {len(response.data)})."
        )
    except Exception as exc:
        print(f"BŁĄD podczas komunikacji z Supabase: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
