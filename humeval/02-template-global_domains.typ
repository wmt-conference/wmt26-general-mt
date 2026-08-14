#set page(height: auto, width: auto, margin: 0pt)
#let data = json(bytes(sys.inputs.data))
// LaTeX ACL font
#set text(font: "New Computer Modern", size: 10pt)

#let round(x, digits: 2) = {
  if digits == 0 { return str(calc.round(x, digits: 0)) }
  
  let s = str(calc.round(x, digits: digits))
  let parts = s.split(".")
  
  if parts.len() == 1 {
    parts.push("")
  }
  
  parts.at(0) + "." + parts.at(1) + "0" * (digits - parts.at(1).len())
}


#let colored_cell = x => {
  if x == -100 {
    return table.cell(fill: luma(220), [])
  }
  table.cell(fill: luma(300).mix((green, x/100*7), (red, (1 - x/100)*7)), round(x, digits: 1))
}

#let format_pair = pair => {
  if pair.contains("---") {
    let (l1, l2) = pair.split("---")
    let format_src = l => if l == "English" { "En." } else if l == "Czech" { "Cz." } else if l == "Simplified Chinese" { "Zh." } else { l }
    let format_tgt = l => l.replace("Traditional Chinese", "Chinese (Trad.)").replace("Simplified Chinese", "Chinese (Simp.)").replace("Egyptian Arabic", "Arabic (Egy.)").replace("Serbian", "Serbian (Cyr.)")
    format_src(l1) + sym.arrow + format_tgt(l2)
  } else {
    pair
  }
}

#let domains = data.at(0).at(1).keys()

#table(
  columns: (auto,) + (0.8cm, ) * domains.len(),
  inset: 4pt,
  rows: auto,
  align: (horizon+left,) + (horizon+center, ) * domains.len(),
  stroke: none,
  table.hline(),
  [], ..domains.map(d => align(bottom + center, rotate(-90deg, reflow: true, strong(d)))),
  table.hline(),
  ..data.map(row => {
    (format_pair(row.at(0)), ..domains.map(d => colored_cell(row.at(1).at(d, default: -100))))
  }).flatten(),
  table.hline(),
)