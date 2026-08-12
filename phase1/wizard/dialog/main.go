// 😈 Syntropia Apps TUI — the glamorous pick-your-apps dialog.
//
// A Bubble Tea (Charm ecosystem) dialog: dark glamour theme, category
// groups, keyboard-first checkbox list. Prints the checked package tags,
// one per line, to stdout — the same contract as `kdialog --checklist
// --separate-output` — so the wizard parses it identically. Exit 0 = OK,
// 1 = cancelled.
//
// Dependencies: none at runtime (static binary). Built from source with
// the Go toolchain (bubbletea + lipgloss), which the PKGBUILD does via
// makedepends.
//
// Usage: syntropia-apps-tui <apps.list>

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
	bg      = "#0e0a1c" // deep purple-black
	panel   = "#221640" // cursor highlight
	accent  = "#a78bfa" // violet — category headers
	hot     = "#ff6ec7" // hot pink — checks, count
	textC   = "#ece5f8" // near-white lavender
	dimC    = "#8f7fb3" // muted hints
	borderC = "#3b2a63" // outer border
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
		if i := strings.Index(line, "#"); i >= 0 {
			line = line[:i]
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
		g.items = append(g.items, &item{name: name, pkg: pkg, desc: desc, checked: true})
	}
	out := make([]group, 0, len(groups))
	for _, g := range groups {
		out = append(out, *g)
	}
	return out, nil
}

// ---------- gradient title ----------

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
		fmt.Fprintf(&b, "\x1b[38;2;%d;%d;%dm%c", r, g, bl, s[i])
	}
	b.WriteString("\x1b[0m")
	return b.String()
}

// ---------- model ----------

type model struct {
	groups []group
	flat   []*item // cursor walks the flattened list (catalog order)
	cursor int
	width  int
	height int
	done   bool
	cancel bool
}

func newModel(groups []group) model {
	m := model{groups: groups}
	for gi := range m.groups {
		for ii := range m.groups[gi].items {
			m.flat = append(m.flat, m.groups[gi].items[ii])
		}
	}
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
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j", "ctrl+n":
			if m.cursor < len(m.flat)-1 {
				m.cursor++
			}
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
			m.flat[m.cursor].checked = !m.flat[m.cursor].checked
		case "a", "A":
			for _, it := range m.flat {
				it.checked = true
			}
		case "n", "N":
			for _, it := range m.flat {
				it.checked = false
			}
		case "enter":
			m.done = true
			return m, tea.Quit
		}
	}
	return m, nil
}

func (m model) itemLine(it *item, idx, innerW int) string {
	cursor := idx == m.cursor

	box := "[ ]"
	boxStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(dimC))
	if it.checked {
		box = "[✓]"
		boxStyle = lipgloss.NewStyle().Foreground(lipgloss.Color(hot))
	}
	prefix := "  "
	if cursor {
		prefix = "▶ "
	}
	nameStyle := lipgloss.NewStyle().Foreground(lipgloss.Color(textC))
	if cursor {
		nameStyle = nameStyle.Bold(true)
	}
	line := prefix + boxStyle.Render(box) + " " + nameStyle.Render(it.name)

	if it.desc != "" && !cursor {
		descW := lipgloss.Width(it.desc)
		pad := innerW - lipgloss.Width(line) - descW - 2
		if pad > 4 {
			line += strings.Repeat(" ", pad) + lipgloss.NewStyle().Foreground(lipgloss.Color(dimC)).Render(it.desc)
		}
	}
	if cursor {
		line = lipgloss.NewStyle().Background(lipgloss.Color(panel)).Width(innerW).Render(line)
	}
	return line
}

func (m model) View() string {
	w := m.width
	if w <= 0 {
		w = 80
	}
	if w > 76 {
		w = 76
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

	// header
	title := lipgloss.NewStyle().Bold(true).Render(gradientText("😈 SYNTROPIA", gradFrom, gradTo))
	sub := lipgloss.NewStyle().Foreground(lipgloss.Color(dimC)).Render("pick your apps — everything installs together")
	header := lipgloss.JoinVertical(lipgloss.Left, title, sub)

	// body
	var lines []string
	for gi := range m.groups {
		lines = append(lines, lipgloss.NewStyle().Bold(true).
			Foreground(lipgloss.Color(accent)).
			Render("✦ "+strings.ToUpper(m.groups[gi].name)))
		for ii := range m.groups[gi].items {
			idx := 0
			for fi := range m.flat {
				if m.flat[fi] == m.groups[gi].items[ii] {
					idx = fi
					break
				}
			}
			lines = append(lines, m.itemLine(m.groups[gi].items[ii], idx, innerW))
		}
	}

	// footer
	hint := lipgloss.NewStyle().Foreground(lipgloss.Color(dimC)).
		Render("↑/↓ move · space toggle · a all · n none · enter install · esc cancel")
	count := lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color(hot)).
		Render(fmt.Sprintf("%d/%d selected", m.selectedCount(), len(m.flat)))
	pad := innerW - lipgloss.Width(hint) - lipgloss.Width(count) - 1
	if pad < 1 {
		pad = 1
	}
	footer := hint + strings.Repeat(" ", pad) + count

	// scroll: keep the cursor row visible
	ch := h - 1 - lipgloss.Height(header) - 1 // footer + border rows
	if ch < 1 {
		ch = 1
	}
	off := 0
	if len(lines) > ch {
		if m.cursor < off {
			off = m.cursor
		}
		if m.cursor >= off+ch {
			off = m.cursor - ch + 1
		}
	}
	end := off + ch
	if end > len(lines) {
		end = len(lines)
	}
	body := strings.Join(lines[off:end], "\n")

	content := lipgloss.JoinVertical(lipgloss.Left, header, body, footer)
	box := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color(borderC)).
		Background(lipgloss.Color(bg)).
		Padding(0, 1).
		Width(w - 2).
		Render(content)
	// paint the full terminal background so the glamour theme fills the screen
	return lipgloss.NewStyle().Background(lipgloss.Color(bg)).Render(box)
}

// ---------- main ----------

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: syntropia-apps-tui <apps.list>")
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
	for _, it := range mf.flat {
		if it.checked {
			fmt.Println(it.pkg)
		}
	}
}
