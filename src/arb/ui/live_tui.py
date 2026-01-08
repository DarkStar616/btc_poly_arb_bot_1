import asyncio
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from datetime import datetime

class LiveDashboard:
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="logs", size=10)
        )
        self.layout["body"].split_row(
            Layout(name="market"),
            Layout(name="strategy")
        )
        self.logs = []

    def make_header(self, state):
        status = state.get('state', 'INIT')
        # Color code status
        color = "green" if status == "RUNNING" else "yellow" if status == "PAUSED" else "red"
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right", ratio=1)
        grid.add_row(
            f"Polymarket Paper Arb | Status: [{color}]{status}[/{color}]",
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return Panel(grid, style=f"on { 'black' }")

    def make_market_panel(self, snap):
        # Market Info
        m_table = Table(title="Market / Feeds")
        m_table.add_column("Metric", style="cyan")
        m_table.add_column("Value", style="white")
        
        m_table.add_row("Question", snap.get('market', 'Finding...'))
        
        # Health / Lag
        h = snap.get('health', {})
        m_table.add_row("Poly Lag", f"{h.get('poly_lag_ms',0):.1f} ms")
        m_table.add_row("Binance Lag", f"{h.get('binance_lag_ms',0):.1f} ms")
        
        # Gates
        gates = snap.get('gates', [])
        if gates:
            m_table.add_row("GATES", f"[red]{','.join(gates)}[/red]")
        
        # Book
        by = snap.get('book_yes', (0,0))
        bn = snap.get('book_no', (0,0))
        m_table.add_row("YES Book", f"{by[0]:.3f} / {by[1]:.3f}")
        m_table.add_row("NO Book", f"{bn[0]:.3f} / {bn[1]:.3f}")

        return Panel(m_table)

    def make_strategy_panel(self, snap):
        # Strategy / Account
        s_table = Table(title="Strategy / Account")
        s_table.add_column("Metric", style="magenta")
        s_table.add_column("Value", style="green")
        
        ft = snap.get('features', {})
        s_table.add_row("Ret 30s", f"{ft.get('ret_30s',0)*100:.4f}%")
        s_table.add_row("Trade Count", str(ft.get('trade_count_10s',0)))
        
        # Account
        # snap['account'] is string repr
        s_table.add_row("Account", str(snap.get('account', '')))
        
        return Panel(s_table)

    async def run(self, queue):
        with Live(self.layout, refresh_per_second=4, screen=True) as live:
            while True:
                try:
                    snap = await queue.get()
                    
                    self.layout["header"].update(self.make_header(snap))
                    self.layout["market"].update(self.make_market_panel(snap))
                    self.layout["strategy"].update(self.make_strategy_panel(snap))
                    
                    # Log handling (simple placeholder)
                    self.layout["logs"].update(Panel("Logs stream..."))
                    
                except asyncio.CancelledError:
                    break
