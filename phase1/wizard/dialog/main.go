// 😈 Syntropia Apps TUI — the glamorous pick-your-apps dialog.
//
// A Bubble Tea (Charm ecosystem) dialog: dark glamour theme, category
// groups, keyboard-first checkbox list. Prints the checked package tags,
// one per line, to stdout — the same contract as `kdialog --checklist
// --separate-output` — so the wizard parses it identically. Exit 0 = OK,
// 1 = cancelled.
//
// When an output-file path is given as the second argument, the checked
// tags are ALSO written there (one per line) — the wizard uses that so it
// can run the TUI with its stdout on the real terminal (command
// substitution would pipe the UI away) and still capture the picks.
//
// Dependencies: none at runtime (static binary). Built from source with
// the Go toolchain (bubbletea + lipgloss).
//
// Usage: syntropia-apps-tui <apps.list> [output-file]

package main

import (
	"fmt"
	"os"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// ---------- palette (glamour: deep purple-black + violet/hot-pink) ----------

const (
	bg       = "#0e0a1c" // deep purple-black
	panel    = "#221640" // cursor highlight
	accent   = "#a78bfa" // violet — category headers
	hot      = "#ff6ec7" // hot pink — checks, count
	textC    = "#ece5f8" // near-white lavender
	dimC     = "#8f7fb3" // muted hints
	borderC  = "#3b2a63" // outer border
	gradFrom = "#8b5cf6"
	gradTo   = "#ff6ec7"
)

// ---------- catalog ----------

type item struct {
	name, pkg, desc string
	checked         bool
}

type group struct {
	name  string
	items []*item
}

func loadCatalog(path string) ([]group, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var groups []*group
	byName := map[string]*group{}
	for _, line := range strings.Split(string(raw), "\n") {
		// a '#' starts a comment only at the start of a line or after
		// whitespace, so https:// URLs with a '#fragment' survive intact
		commentAt := -1
		for j, c := range line {
			if c == '#' && (j == 0 || line[j-1] == ' ' || line[j-1] == '\t') {
				commentAt = j
				break
			}
		}
		if commentAt >= 0 {
			line = line[:commentAt]
		}
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.Split(line, "|")
		if len(parts) < 3 {
			continue
		}
		cat := strings.TrimSpace(parts[0])
		name := strings.TrimSpace(parts[1])
		pkg := strings.TrimSpace(parts[2])
		if pkg == "" {
			continue
		}
		desc := ""
		if len(parts) > 3 {
			desc = strings.TrimSpace(parts[3])
		}
		g, ok := byName[cat]
		if !ok {
			g = &group{name: cat}
			byName[cat] = g
			groups = append(groups, g)
		}
		g.items = append(g.items, &item{name: name, pkg: pkg, desc: desc, checked: false})
	}
	out := make([]group, 0, len(groups))
	for _, g := range groups {
		out = append(out, *g)
	}
	return out, nil
}

// ---------- gradient title ----------

// The ASCII-art banner — oh-my-logo Slant font, 52 cols × 5 rows.
// Generated: oh-my-logo "SYNTROPIA" sunset --font Slant
// CC0 licensed (oh-my-logo logos are public domain). Colors applied
// per-row by gradientText to give a violet→pink horizontal sweep.
const bannerArt = `   _______  ___   ____________  ____  ____  _______ 
  / ___/\ \/ / | / /_  __/ __ \/ __ \/ __ \/  _/   |
  \__ \  \  /  |/ / / / / /_/ / / / / /_/ // // /| |
 ___/ /  / / /|  / / / / _, _/ /_/ / ____// // ___ |
/____/  /_/_/ |_/ /_/ /_/ |_|\____/_/   /___/_/  |_|`

func lerpByte(a, b byte, t float64) byte {
	return byte(float64(a) + (float64(b)-float64(a))*t)
}

func hexToRGB(s string) [3]byte {
	s = strings.TrimPrefix(s, "#")
	var r, g, b byte
	if len(s) == 6 {
		fmt.Sscanf(s, "%02x%02x%02x", &r, &g, &b)
	}
	return [3]byte{r, g, b}
}

// gradientText renders each character in a color interpolated from -> to.
func gradientText(s, fromHex, toHex string) string {
	from, to := hexToRGB(fromHex), hexToRGB(toHex)
	var b strings.Builder
	n := len(s)
	for i := 0; i < n; i++ {
		t := 0.0
		if n > 1 {
			t = float64(i) / float64(n-1)
		}
		r := lerpByte(from[0], to[0], t)
		g := lerpByte(from[1], to[1], t)
		bl := lerpByte(from[2], to[2], t)
		// paint the theme background on every character so the banner never
		// falls through to the terminal's default background
		fmt.Fprintf(&b, "\x1b[38;2;%d;%d;%dm\x1b[48;2;14;10;28m%c", r, g, bl, s[i])
	}
	b.WriteString("\x1b[0m")
	return b.String()
}

// seg renders one segment with the theme background baked in. Nested style
// resets (\x1b[0m) clear the background attribute, so without this every
// styled segment would fall through to the terminal's default background.
func seg(bgC, fgC string, bold bool, s string) string {
	st := lipgloss.NewStyle().Background(lipgloss.Color(bgC)).Foreground(lipgloss.Color(fgC))
	if bold {
		st = st.Bold(true)
	}
	return st.Render(s)
}

// ---------- model ----------

// cellPos is an item's position in the rendered grid.
type cellPos struct {
	col, row int // col = grid column, row = line index within that column
}

type model struct {
	groups   []group
	flat     []*item // catalog order
	flatIdx  map[*item]int
	doneItem *item // sentinel "Done" row (index == len(flat))
	cursor   int
	width    int
	height   int
	done     bool
	cancel   bool

	// grid navigation state (rebuilt when the width changes)
	ncols     int
	itemPos   map[int]cellPos // flat index -> grid position
	posToItem map[cellPos]int // grid position -> flat index
	doneFrom  int             // where the cursor was before stepping onto Done
}

func newModel(groups []group) model {
	m := model{groups: groups, flatIdx: map[*item]int{}}
	for gi := range m.groups {
		for ii := range m.groups[gi].items {
			m.flatIdx[m.groups[gi].items[ii]] = len(m.flat)
			m.flat = append(m.flat, m.groups[gi].items[ii])
		}
	}
	// the Done sentinel lives one past the last real item; it is not part of
	// any group or the picks list — only reachable via the navigation keys
	m.doneItem = &item{name: "Done", pkg: "", desc: "install the selected apps and finish"}
	return m
}

func (m model) selectedCount() int {
	n := 0
	for _, it := range m.flat {
		if it.checked {
			n++
		}
	}
	return n
}

// ncolsFor decides how many grid columns fit a terminal width.
func ncolsFor(w int) int {
	innerW := w - 4 // border (2) + box padding (2)
	nc := innerW / 22
	if nc > maxCols {
		nc = maxCols
	}
	if nc < 1 {
		nc = 1
	}
	return nc
}

// buildGrid maps every item to its (column, row) position for navigation.
func (m *model) buildGrid(ncols int) {
	m.ncols = ncols
	m.itemPos = map[int]cellPos{}
	m.posToItem = map[cellPos]int{}
	cols := packGroups(m.groups, ncols)
	for ci := range cols {
		row := 0
		for _, gi := range cols[ci] {
			row++ // header row
			for ii := range m.groups[gi].items {
				it := m.groups[gi].items[ii]
				idx := m.flatIdx[it]
				m.itemPos[idx] = cellPos{ci, row}
				m.posToItem[cellPos{ci, row}] = idx
				row++
			}
		}
	}
}

// ensureGrid rebuilds the nav map if the column count changed.
func (m *model) ensureGrid() {
	nc := ncolsFor(m.width)
	if nc != m.ncols || m.itemPos == nil {
		m.buildGrid(nc)
	}
}

// doneIdx is the grid position of the Done sentinel row.
func (m model) doneIdx() int { return len(m.flat) }

// onDone reports whether the cursor sits on the Done row.
func (m model) onDone() bool { return m.cursor == m.doneIdx() }

// moveUp/down stay within the current column; at the column edge they clamp.
// From the bottom of the grid, down steps onto the Done row; up from Done
// returns to the last real item.
func (m *model) moveUp() {
	m.ensureGrid()
	if m.onDone() {
		m.cursor = m.doneFrom
		return
	}
	pos, ok := m.itemPos[m.cursor]
	if !ok {
		return
	}
	for i := m.cursor - 1; i >= 0; i-- {
		if m.itemPos[i].col == pos.col {
			m.cursor = i
			return
		}
	}
}

func (m *model) moveDown() {
	m.ensureGrid()
	if m.onDone() {
		return
	}
	pos, ok := m.itemPos[m.cursor]
	if !ok {
		return
	}
	for i := m.cursor + 1; i < len(m.flat); i++ {
		if m.itemPos[i].col == pos.col {
			m.cursor = i
			return
		}
	}
	// bottom of any column: down steps onto the Done row (remembering where
	// we came from so up can return)
	m.doneFrom = m.cursor
	m.cursor = m.doneIdx()
}

// moveCol jumps to the adjacent column, landing on the item closest to the
// current vertical position. From the Done row, left/right return to the grid.
func (m *model) moveCol(d int) {
	m.ensureGrid()
	if m.onDone() {
		m.cursor = m.doneFrom
		return
	}
	pos, ok := m.itemPos[m.cursor]
	if !ok {
		return
	}
	target := pos.col + d
	if target < 0 || target >= m.ncols {
		return
	}
	best, bestDist := -1, 1<<30
	for idx, p := range m.itemPos {
		if p.col != target {
			continue
		}
		dist := p.row - pos.row
		if dist < 0 {
			dist = -dist
		}
		if dist < bestDist || (dist == bestDist && idx < best) {
			best, bestDist = idx, dist
		}
	}
	if best != -1 {
		m.cursor = best
	}
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q", "esc":
			m.cancel = true
			return m, tea.Quit
		case "up", "k", "ctrl+p":
			m.moveUp()
		case "down", "j", "ctrl+n":
			m.moveDown()
		case "left", "h":
			m.moveCol(-1)
		case "right", "l":
			m.moveCol(1)
		case "pgup", "ctrl+u":
			m.cursor -= 8
			if m.cursor < 0 {
				m.cursor = 0
			}
		case "pgdown", "ctrl+d":
			m.cursor += 8
			if m.cursor >= len(m.flat) {
				m.cursor = len(m.flat) - 1
			}
		case " ":
			// space toggles: apps get checked/unchecked; the Done row gets
			// armed/disarmed. It never quits by itself.
			if m.onDone() {
				m.doneItem.checked = !m.doneItem.checked
			} else {
				m.flat[m.cursor].checked = !m.flat[m.cursor].checked
			}
		case "enter":
			// enter only installs once Done has been armed with space
			if m.onDone() && m.doneItem.checked {
				m.done = true
				return m, tea.Quit
			}
		case "a", "A":
			for _, it := range m.flat {
				it.checked = true
			}
		case "n", "N":
			for _, it := range m.flat {
				it.checked = false
			}
		}
	}
	return m, nil
}

// The grid spreads the catalog across up to maxCols columns, filling the
// full terminal width. Groups are packed into columns in catalog order,
// balancing each column's rendered height (header + items).
const maxCols = 5

// packGroups splits group indices across n columns in catalog order.
func packGroups(groups []group, n int) [][]int {
	heights := make([]int, len(groups))
	total := 0
	for gi := range groups {
		heights[gi] = 1 + len(groups[gi].items)
		total += heights[gi]
	}
	if n < 1 {
		n = 1
	}
	if n > len(groups) {
		n = len(groups)
	}
	target := (total + n - 1) / n
	cols := make([][]int, n)
	ci, cur := 0, 0
	for gi := range groups {
		if ci < n-1 && cur > 0 && cur+heights[gi] > target {
			ci++
			cur = 0
		}
		cols[ci] = append(cols[ci], gi)
		cur += heights[gi]
	}
	return cols
}

// itemCell renders one checkbox row inside a grid column of the given width.
// Cells are always exactly one line wide: content is truncated to the cell
// width, then padded so the columns line up (and the cursor highlight fills
// the whole cell). Descriptions live on the footer status line instead.
func (m model) itemCell(it *item, idx, cellW int) string {
	cursor := idx == m.cursor
	cellBg := bg
	if cursor {
		cellBg = panel
	}

	box := "[ ]"
	boxFg := dimC
	if it.checked {
		box = "[✓]"
		boxFg = hot
	}
	prefix := "  "
	if cursor {
		prefix = "▶ "
	}
	// every segment carries the background so the highlight (and the theme)
	// fill the whole cell, including the padding
	line := seg(cellBg, textC, false, prefix) +
		seg(cellBg, boxFg, false, box) +
		seg(cellBg, textC, false, " ") +
		seg(cellBg, textC, cursor, it.name)

	// truncate to the cell width, then pad with the same background
	trunc := lipgloss.NewStyle().MaxWidth(cellW).Render(line)
	if pad := cellW - lipgloss.Width(trunc); pad > 0 {
		trunc += seg(cellBg, textC, false, strings.Repeat(" ", pad))
	}
	return trunc
}

func (m model) View() string {
	w := m.width
	if w <= 0 {
		w = 120
	}
	if w < 42 {
		w = 42
	}
	h := m.height
	if h <= 0 {
		h = 24
	}
	if h < 9 {
		h = 9
	}
	innerW := w - 4 // border (2) + box padding (2)

	// how many columns fit comfortably? fill the width up to maxCols.
	m.ensureGrid()
	ncols := m.ncols
	const gap = 2
	colW := (innerW - (ncols-1)*gap) / ncols // subtract the inter-column gaps so rows fit exactly

	// header — big gradient banner when there's room, compact title otherwise
	var title string
	bannerW := lipgloss.Width(strings.Split(bannerArt, "\n")[0])
	if h >= 12 && innerW >= bannerW {
		// fade each row left→right so the whole banner sweeps violet→pink
		var rows []string
		for _, ln := range strings.Split(bannerArt, "\n") {
			rows = append(rows, gradientText(ln, gradFrom, gradTo))
		}
		title = lipgloss.NewStyle().Align(lipgloss.Center).Width(innerW).
			Background(lipgloss.Color(bg)).
			Render(strings.Join(rows, "\n"))
	} else {
		title = lipgloss.NewStyle().Bold(true).Align(lipgloss.Center).Width(innerW).
			Background(lipgloss.Color(bg)).
			Render(gradientText("😈 SYNTROPIA", gradFrom, gradTo))
	}
	sub := lipgloss.NewStyle().Foreground(lipgloss.Color(dimC)).
		Background(lipgloss.Color(bg)).
		Align(lipgloss.Center).Width(innerW).
		Render("pick your apps — everything installs together")
	header := lipgloss.JoinVertical(lipgloss.Left, title, sub)

	// pack groups into columns and render each column's lines
	cols := packGroups(m.groups, ncols)
	cursorRow := 0
	colLines := make([][]string, ncols)
	for ci := range cols {
		var lines []string
		for _, gi := range cols[ci] {
			hdr := lipgloss.NewStyle().Bold(true).
				Foreground(lipgloss.Color(accent)).
				Background(lipgloss.Color(bg)).
				Render("✦ " + strings.ToUpper(m.groups[gi].name))
			if pad := colW - lipgloss.Width(hdr); pad > 0 {
				hdr += seg(bg, accent, false, strings.Repeat(" ", pad))
			}
			lines = append(lines, hdr)
			for ii := range m.groups[gi].items {
				it := m.groups[gi].items[ii]
				idx := m.flatIdx[it]
				if idx == m.cursor {
					cursorRow = len(lines)
				}
				lines = append(lines, m.itemCell(it, idx, colW))
			}
		}
		colLines[ci] = lines
	}

	// pad columns to equal height, then join into rows
	maxH := 0
	for ci := range colLines {
		if len(colLines[ci]) > maxH {
			maxH = len(colLines[ci])
		}
	}
	rows := make([]string, maxH)
	for r := 0; r < maxH; r++ {
		cells := make([]string, ncols)
		for ci := 0; ci < ncols; ci++ {
			if r < len(colLines[ci]) {
				cells[ci] = colLines[ci][r]
			} else {
				cells[ci] = seg(bg, textC, false, strings.Repeat(" ", colW))
			}
		}
		row := strings.Join(cells, seg(bg, textC, false, strings.Repeat(" ", gap)))
		// pad to the full inner width with the theme background so
		// JoinVertical has no unpainted spaces to add later
		if pad := innerW - lipgloss.Width(row); pad > 0 {
			row += seg(bg, textC, false, strings.Repeat(" ", pad))
		}
		rows[r] = row
	}

	// the Done button — a full-width confirm row below the grid. Space arms
	// it (like a checkbox); enter only installs once it's armed. Escape
	// cancels. Enter/space on apps never exits.
	doneBox := "[ ]"
	doneBoxFg := dimC
	doneTxt := "DONE — install " + fmt.Sprintf("%d apps", m.selectedCount())
	if m.doneItem.checked {
		doneBox = "[✓]"
		doneBoxFg = hot
		doneTxt = "DONE — install " + fmt.Sprintf("%d apps", m.selectedCount()) + " (press enter)"
	}
	doneBg := bg
	if m.onDone() {
		doneBg = panel
	}
	doneRow := seg(doneBg, doneBoxFg, false, doneBox) + seg(doneBg, textC, false, " ") +
		seg(doneBg, hot, true, doneTxt)
	if pad := innerW - lipgloss.Width(doneRow); pad > 0 {
		doneRow += seg(doneBg, textC, false, strings.Repeat(" ", pad))
	}
	rows = append(rows, seg(bg, textC, false, strings.Repeat(" ", innerW))) // spacer
	if m.onDone() {
		cursorRow = len(rows)
	}
	rows = append(rows, doneRow)

	// footer — cursor item's description on a status line, then hints + count
	var cur *item
	if m.onDone() {
		cur = m.doneItem
		if m.doneItem.checked {
			cur.desc = "armed — press enter to install the selected apps"
		} else {
			cur.desc = "press space to arm, then enter to install"
		}
	} else {
		cur = m.flat[m.cursor]
	}
	status := seg(bg, accent, false, "▶ "+cur.name) + seg(bg, dimC, false, "  "+cur.desc)
	status = lipgloss.NewStyle().Background(lipgloss.Color(bg)).Width(innerW).Align(lipgloss.Center).
		Render(status)
	count := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(hot)).
		Background(lipgloss.Color(bg)).
		Render(fmt.Sprintf("%d/%d selected", m.selectedCount(), len(m.flat)))
	hintTxt := "↑/↓ move · ←/→ column · space toggle · a all · n none · space on DONE arms · enter installs · esc cancel"
	if lipgloss.Width(hintTxt)+4+lipgloss.Width(count) > innerW {
		// narrow terminal: compress the hints so the line never wraps
		hintTxt = "↑/↓ · ←/→ move · space toggle · space on DONE arms · enter installs · esc"
	}
	hint := lipgloss.NewStyle().Foreground(lipgloss.Color(dimC)).
		Background(lipgloss.Color(bg)).Render(hintTxt)
	hintLine := lipgloss.NewStyle().Background(lipgloss.Color(bg)).Width(innerW).Align(lipgloss.Center).
		Render(hint + seg(bg, dimC, false, "   ") + count)
	footer := lipgloss.JoinVertical(lipgloss.Left, status, hintLine)

	// scroll: keep the cursor row visible
	ch := h - 1 - lipgloss.Height(header) - lipgloss.Height(footer) // border rows
	if ch < 1 {
		ch = 1
	}
	off := 0
	if len(rows) > ch {
		if cursorRow < off {
			off = cursorRow
		}
		if cursorRow >= off+ch {
			off += cursorRow - (off + ch) + 1 // advance the window, don't jump it
		}
		if off+ch > len(rows) {
			off = len(rows) - ch
		}
	}
	end := off + ch
	if end > len(rows) {
		end = len(rows)
	}
	body := strings.Join(rows[off:end], "\n")

	content := lipgloss.JoinVertical(lipgloss.Left, header, body, footer)
	// no explicit Width: rows are already exactly innerW wide, so the box
	// renders border+padding+content = exactly w columns with no unpainted
	// right-edge padding leaking the terminal's default background through
	box := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color(borderC)).
		Background(lipgloss.Color(bg)).
		Padding(0, 1).
		Render(content)
	// paint the full terminal background so the glamour theme fills the screen
	return lipgloss.NewStyle().Background(lipgloss.Color(bg)).Render(box)
}

// ---------- main ----------

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: syntropia-apps-tui <apps.list> [output-file]")
		os.Exit(2)
	}
	groups, err := loadCatalog(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, "😈 error:", err)
		os.Exit(2)
	}
	if len(groups) == 0 {
		fmt.Fprintln(os.Stderr, "😈 error: empty catalog:", os.Args[1])
		os.Exit(2)
	}
	var outFile string
	if len(os.Args) > 2 {
		outFile = os.Args[2]
	}

	p := tea.NewProgram(newModel(groups), tea.WithAltScreen())
	final, err := p.Run()
	if err != nil {
		fmt.Fprintln(os.Stderr, "😈 error:", err)
		os.Exit(1)
	}
	mf := final.(model)
	if mf.cancel {
		os.Exit(1)
	}
	var picks []string
	for _, it := range mf.flat {
		if it.checked {
			picks = append(picks, it.pkg)
		}
	}
	if outFile != "" {
		if err := os.WriteFile(outFile, []byte(strings.Join(picks, "\n")+"\n"), 0o644); err != nil {
			fmt.Fprintln(os.Stderr, "😈 error writing", outFile+":", err)
			os.Exit(1)
		}
	}
	for _, p := range picks {
		fmt.Println(p)
	}
}
