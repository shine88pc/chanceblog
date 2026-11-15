# independent WCAG contrast recomputation (no repo imports)
def lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
def lum(h):
    h = h.lstrip('#')
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
W = '#FFFFFF'
for name, col in [('text_muted', '#8491A3'), ('text_secondary', '#5F6B7A'), ('border_strong', '#B8C7DA'), ('border', '#DCE4F0'), ('secondary_border', '#AFC1D8'), ('text_disabled', '#AAB4C3')]:
    print(f"{name:18s} {col}  on white {contrast(col, W):.4f}")
print("--- grounds for secondary and muted")
for g_name, g in [('surface', '#FFFFFF'), ('surface_2', '#F8FAFD'), ('bg_app', '#F4F7FB'), ('surface_selected', '#EEF5FF'), ('surface_hover', '#F4F8FF'), ('bg_sidebar', '#F7F9FC'), ('primary_100', '#EAF2FF')]:
    print(f"{g_name:18s} {g}  secondary {contrast('#5F6B7A', g):.3f}  muted {contrast('#8491A3', g):.3f}")
