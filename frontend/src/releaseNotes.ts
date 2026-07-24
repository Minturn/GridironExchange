// Bump APP_VERSION when shipping user-facing changes and add a RELEASE_NOTES entry
// at the top. The masthead shows this version; if it differs from the server's
// version (from /api/state), the app nudges a reload — so everyone can confirm
// they're on the same build.
export const APP_VERSION = '0.6.0'

export interface Release {
  version: string
  date: string
  notes: string[]
}

export const RELEASE_NOTES: Release[] = [
  {
    version: '0.6.0',
    date: 'Jul 23, 2026',
    notes: [
      'New “Cash Ledger” tab — every dollar in and out, newest first: your opening balance, each buy and sell (with fee), and each dividend, with your running cash after each. No more wondering where your balance came from.',
      'Your ledger reconciles: the app replays your trades and dividends and confirms they add up to your cash, to the cent — with a ✓ when they agree.',
      'Reminder it makes obvious: cash only goes up when you sell or a dividend pays. In the offseason there are no dividends yet, so a bigger balance means you sold.',
      'Commissioner: a “Money audit” card checks every member’s books against their cash in one click and flags any mismatch.',
    ],
  },
  {
    version: '0.5.0',
    date: 'Jul 9, 2026',
    notes: [
      'New “Scoring” chip in the header — tap it for a plain-English guide to how your league’s mode (market / relative / lineup) turns points into dividends.',
      'Dividends now settle by a kickoff snapshot: you earn a player’s points by owning him before his game, so nobody can buy in after kickoff just to grab a dividend.',
      'Commissioner: In-game trading switch — keep stocks locked at kickoff (default) or “Go live” to trade during games. A “● Live” badge shows when it’s on.',
      'Commissioner now shows the current scoring mode and dividend rate, with a heads-up before a mid-season change.',
    ],
  },
  {
    version: '0.4.0',
    date: 'Jul 6, 2026',
    notes: [
      'The Floor now has search and position filters (QB/RB/WR/TE).',
      'Lineup is sorted by position, and you can tap ↗ next to a player to open them and buy or sell.',
      'Your Lineup shows the roster requirements (1 QB · 2 RB · 3 WR · 1 TE · 1 FLEX) and whether it’s full.',
      'Tap any name in Standings to see their roster — a ★ marks the players in their starting lineup.',
      'Commissioner: searchable stat correction, adjustable dividend rate, and market/relative/lineup scoring.',
      'This “What’s New” — tap the version chip anytime to confirm everyone’s on the same build.',
    ],
  },
  {
    version: '0.3.0',
    date: 'Jul 6, 2026',
    notes: [
      'Scoring modes: market, relative (position-balanced), and lineup — fixes “all QBs win”.',
      'Commissioner-set Week-1 start time with a live countdown so everyone starts together.',
      'Mobile layout + add-to-home-screen with a proper app icon.',
      'Case-insensitive login.',
    ],
  },
]
