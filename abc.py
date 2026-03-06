import re
import math
import requests
from decimal import Decimal, getcontext
getcontext().prec = 50

TEST_NAME = "Static"

URL = "https://raw.githubusercontent.com/kataras/server-benchmarks/master/README.md"

response = requests.get(URL, timeout=30)
response.raise_for_status()
markdown_text = response.text

def to_decimal(x):
    """Convert to Decimal safely."""
    return Decimal(str(x))

def fmt(x):
    """
    Format numbers to 10 decimal places.
    Works for float, int, Decimal.
    """
    if isinstance(x, Decimal):
        return f"{x:.10f}"
    return f"{float(x):.10f}"

def parse_latency_to_ms(latency_str):
    """
    Convert latency string to milliseconds.
    Examples:
        '438.34us' -> 0.43834 ms
        '0.93ms'   -> 0.93 ms
        '1.08ms'   -> 1.08 ms
    """
    s = latency_str.strip().lower()

    match = re.match(r"^([0-9]*\.?[0-9]+)\s*(us|ms|s)$", s)
    if not match:
        raise ValueError(f"Could not parse latency value: {latency_str}")

    value = Decimal(match.group(1))
    unit = match.group(2)

    if unit == "us":
        return value / Decimal("1000")
    elif unit == "ms":
        return value
    elif unit == "s":
        return value * Decimal("1000")
    else:
        raise ValueError(f"Unsupported latency unit: {unit}")

def parse_reqs_per_sec(reqs_str):
    """
    Parse Reqs/sec as Decimal.
    Example:
        '284059' -> Decimal('284059')
    """
    s = reqs_str.strip().replace(",", "")
    return Decimal(s)

def extract_test_tables(markdown):
    """
    Parse all benchmark tables under sections like:
        ### Test:Static
        | Name | Language | Reqs/sec | Latency | ...
        |------|...
        | [Iris](...) | Go |284059 |438.34us |...

    Returns:
        dict:
        {
            "Static": [
                {"Name": "Iris", "Language": "Go", "Reqs/sec": "...", "Latency": "...", ...},
                ...
            ],
            ...
        }
    """
    tables = {}

    section_pattern = re.compile(r"^###\s*Test:([^\n]+)", re.MULTILINE)
    matches = list(section_pattern.finditer(markdown))

    for i, match in enumerate(matches):
        test_name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        section_text = markdown[start:end]

        lines = [line.rstrip() for line in section_text.splitlines() if line.strip()]

        # Find markdown table lines
        table_lines = []
        started = False
        for line in lines:
            if line.startswith("|"):
                table_lines.append(line)
                started = True
            elif started:
                break

        if len(table_lines) < 3:
            continue

        header_line = table_lines[0]
        separator_line = table_lines[1]
        data_lines = table_lines[2:]

        headers = [h.strip() for h in header_line.strip("|").split("|")]

        rows = []
        for line in data_lines:
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) != len(headers):
                continue

            row = dict(zip(headers, parts))
            if "Name" in row:
                name_match = re.match(r"\[([^\]]+)\]\([^)]+\)", row["Name"])
                if name_match:
                    row["Name"] = name_match.group(1).strip()

            rows.append(row)

        tables[test_name] = rows

    return tables

all_tables = extract_test_tables(markdown_text)

if TEST_NAME not in all_tables:
    raise ValueError(
        f"TEST_NAME='{TEST_NAME}' not found.\n"
        f"Available tests: {list(all_tables.keys())}"
    )

rows = all_tables[TEST_NAME]

data = []
for row in rows:
    framework = row["Name"]
    reqs = parse_reqs_per_sec(row["Reqs/sec"])
    latency_ms = parse_latency_to_ms(row["Latency"])

    ln_reqs = Decimal(str(math.log(float(reqs))))
    ln_latency_ms = Decimal(str(math.log(float(latency_ms))))

    data.append({
        "Framework": framework,
        "Reqs_per_sec": reqs,
        "Latency_raw": row["Latency"],
        "Latency_ms": latency_ms,
        "ln_Reqs_per_sec": ln_reqs,
        "ln_Latency_ms": ln_latency_ms
    })

print("=" * 90)
print(f"STEP 1: CLEANED DATA USED IN THE REGRESSION ({TEST_NAME} TABLE)")
print("=" * 90)
print(f"{'Framework':<15} {'Reqs/sec':>15} {'Latency raw':>15} {'Latency ms':>18} {'ln(Reqs/sec)':>18} {'ln(Latency ms)':>18}")
print("-" * 90)

for row in data:
    print(
        f"{row['Framework']:<15} "
        f"{fmt(row['Reqs_per_sec']):>15} "
        f"{row['Latency_raw']:>15} "
        f"{fmt(row['Latency_ms']):>18} "
        f"{fmt(row['ln_Reqs_per_sec']):>18} "
        f"{fmt(row['ln_Latency_ms']):>18}"
    )


n = Decimal(len(data))

sum_x = sum(row["ln_Reqs_per_sec"] for row in data)
sum_y = sum(row["ln_Latency_ms"] for row in data)
x_bar = sum_x / n
y_bar = sum_y / n

print("\n" + "=" * 90)
print("STEP 2: SAMPLE SIZE AND MEANS")
print("=" * 90)
print(f"n                 = {fmt(n)}")
print(f"sum_x             = {fmt(sum_x)}")
print(f"sum_y             = {fmt(sum_y)}")
print(f"x_bar             = {fmt(x_bar)}")
print(f"y_bar             = {fmt(y_bar)}")

# Compute Sxx and Sxy
sxx = Decimal("0")
sxy = Decimal("0")

print("\n" + "=" * 90)
print("STEP 3: DEVIATIONS, CROSS PRODUCTS, AND SQUARES")
print("=" * 90)
print(
    f"{'Framework':<15} "
    f"{'x_i - x_bar':>18} "
    f"{'y_i - y_bar':>18} "
    f"{'(x_i-x_bar)^2':>18} "
    f"{'(x_i-x_bar)(y_i-y_bar)':>24}"
)
print("-" * 90)

for row in data:
    dx = row["ln_Reqs_per_sec"] - x_bar
    dy = row["ln_Latency_ms"] - y_bar
    dx2 = dx * dx
    dxdy = dx * dy

    sxx += dx2
    sxy += dxdy

    row["dx"] = dx
    row["dy"] = dy
    row["dx2"] = dx2
    row["dxdy"] = dxdy

    print(
        f"{row['Framework']:<15} "
        f"{fmt(dx):>18} "
        f"{fmt(dy):>18} "
        f"{fmt(dx2):>18} "
        f"{fmt(dxdy):>24}"
    )

print("\n" + "=" * 90)
print("STEP 4: OLS COEFFICIENTS")
print("=" * 90)
print(f"Sxx               = {fmt(sxx)}")
print(f"Sxy               = {fmt(sxy)}")

beta_1 = sxy / sxx
beta_0 = y_bar - beta_1 * x_bar

print(f"beta_1_hat        = Sxy / Sxx = {fmt(beta_1)}")
print(f"beta_0_hat        = y_bar - beta_1_hat * x_bar = {fmt(beta_0)}")

print("\n" + "=" * 130)
print("STEP 5: FITTED LOG VALUES, FITTED LATENCY IN MS, ERRORS, AND SQUARED ERRORS")
print("=" * 130)
print(
    f"{'Framework':<15} "
    f"{'Actual Latency ms':>18} "
    f"{'ln(yhat)':>18} "
    f"{'Fitted Latency ms':>20} "
    f"{'Error':>18} "
    f"{'Error^2':>18}"
)
print("-" * 130)

sse = Decimal("0")

for row in data:
    x_i = row["ln_Reqs_per_sec"]
    yhat_log = beta_0 + beta_1 * x_i
    yhat_ms = Decimal(str(math.exp(float(yhat_log))))
    error = row["Latency_ms"] - yhat_ms
    error2 = error * error

    row["yhat_log"] = yhat_log
    row["yhat_ms"] = yhat_ms
    row["error"] = error
    row["error2"] = error2

    sse += error2

    print(
        f"{row['Framework']:<15} "
        f"{fmt(row['Latency_ms']):>18} "
        f"{fmt(yhat_log):>18} "
        f"{fmt(yhat_ms):>20} "
        f"{fmt(error):>18} "
        f"{fmt(error2):>18}"
    )


print("\n" + "=" * 90)
print("STEP 6: FINAL SSE")
print("=" * 90)
print(f"SSE (unrounded)   = {fmt(sse)}")
print(f"SSE (6 decimals)  = {float(sse):.6f}")

print("\n" + "=" * 90)
print("FITTED MODEL")
print("=" * 90)
print(f"ln(Latency_ms) = {fmt(beta_0)} + {fmt(beta_1)} * ln(Reqs/sec)")
