from __future__ import annotations

from rich.console import Console
from rich.table import Table

from realestate.models import ScoredProperty
from realestate.output import register


@register("table")
class TableFormatter:
    name = "table"

    def format(self, results: list[ScoredProperty], dest: str | None = None) -> None:
        console = Console(file=open(dest, "w") if dest else None)

        t = Table(title="Top Real Estate Deals", show_lines=True)
        t.add_column("#", style="dim", width=4)
        t.add_column("Address", min_width=20)
        t.add_column("City", min_width=10)
        t.add_column("Price", justify="right")
        t.add_column("Beds", justify="center", width=5)
        t.add_column("Sqft", justify="right")
        t.add_column("$/sqft", justify="right")
        t.add_column("Score", justify="right", width=7)
        t.add_column("Top Signal", min_width=20)

        for rank, result in enumerate(results, start=1):
            prop = result.property
            score = result.total_score

            if score >= 70:
                score_style = "bold green"
            elif score >= 40:
                score_style = "yellow"
            else:
                score_style = "red"

            best_score = max(result.scores, key=lambda s: s.value) if result.scores else None
            top_signal = best_score.detail if best_score else ""

            t.add_row(
                str(rank),
                prop.address,
                f"{prop.city}, {prop.state}",
                f"${prop.price:,.0f}",
                str(prop.bedrooms or "-"),
                f"{prop.sqft:,}" if prop.sqft else "-",
                f"${prop.price_per_sqft:,.0f}" if prop.price_per_sqft else "-",
                f"[{score_style}]{score:.1f}[/{score_style}]",
                top_signal,
            )

        console.print(t)
