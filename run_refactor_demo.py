from ranking_pipeline import SpotifyTrack
from track_processor import process_track


tests = [
    {
        "track": SpotifyTrack(
            artist="Sacred Spirit, Dreadzone",
            title="Ya-Na-Hana (Celebrate Wild Rice) - Remix",
            duration=None,
            year=2011,
        ),
        "query": "Sacred Spirit, Dreadzone - Ya-Na-Hana (Celebrate Wild Rice) - Remix",
    },
    {
        "track": SpotifyTrack(
            artist="Sacred Spirit, Mark Brydon",
            title="Heya-Hee (Intertribal Song To Stop The Rain) - Dubbery",
            duration=None,
            year=2011,
        ),
        "query": "Sacred Spirit, Mark Brydon - Heya-Hee (Intertribal Song To Stop The Rain) - Dubbery",
    },
]


if __name__ == "__main__":
    for test in tests:
        result = process_track(
            test["track"],
            exact_query=test["query"],
            top_n=10,
        )

        print("\n" + "=" * 80)
        print("Track:", result["track"]["display_name"])
        print("Exact query   :", result["queries"]["exact"])
        print("Fallback query:", result["queries"]["fallback"])
        print("Used fallback :", result["queries"]["used_fallback"])
        print("Status        :", result["status"])
        print("Counts        :", result["counts"])
        print("=" * 80)

        for candidate in result["ranked_candidates"]:
            print(
                f"[{candidate['score']:>3}] "
                f"{(candidate['extension'] or '?').upper():<4} "
                f"{str(candidate['bitrate'] or '?') + 'kbps':<8} "
                f"{str(candidate['size_mb'] or '?') + 'MB':<8} "
                f"{str(candidate['length'] or '?') + 's':<6} "
                f"{candidate['username']:<18} "
                f"{candidate['filename']}"
            )
            print("  source   :", candidate["source_query"])
            print("  subscores:", candidate["subscores"])
            print("  reasons  :", "; ".join(candidate["reasons"][:4]))
            if candidate["warnings"]:
                print("  warnings :", "; ".join(candidate["warnings"][:4]))
            print()