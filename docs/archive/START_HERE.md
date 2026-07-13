# Start here

A system that prices football transfers. Cost is the amortised fee plus wages. Benefit is the team winning more, converted to money. Subtract, and you get a verdict in pounds.

Two files already work. Both have offline self-checks that pass.

```bash
pip install -r requirements.txt
python impact/wowy.py     # team xG with a player on vs off the pitch
python money/fees.py      # what a transfer should have cost vs what it did
```

Then read `PROMPT.md` (paste into a code session to begin), `SPEC.md` (the full build), `MODELS.md` (which model for which job, and the research still needed) and `DATA.md` (where the data comes from).

## The three ideas that make this different

**Usage is zero-sum.** A team has a fixed budget of shots, key passes and turnovers. A signing who consumes 25% of it takes that 25% off his teammates. So `team_output = Σ (usage × efficiency)`, and a signing only helps if his efficiency beats the average efficiency of the usage he takes. Martial's output collapsed at United because his usage did. Ronaldo took the biggest share of United's attack at an efficiency below the players he displaced. Both are the same equation.

**Efficiency travels, usage doesn't.** Efficiency is a property of the player. Usage is a property of his situation. Split them, and you can price a transfer that hasn't happened yet.

**A player is worth more to some clubs than others.** A club sitting one place off the Champions League values four extra points enormously. A club sitting 14th barely values them. The market charges one price to everyone. That gap is the product.

## Build order

Data → usage and efficiency → WOWY → does usage predict WOWY → league and age curves → fees → money → interface.

Every stage has a test that gates the next one (`SPEC.md §6`). The acceptance test for the impact layer is Manchester United 2021-22. If the engine doesn't say Ronaldo made them worse, it's broken, and nothing built on top of it means anything.
