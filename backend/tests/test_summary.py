from backend.agent.summary import summarize_rows


def _monthly(years=(2020, 2021, 2022)):
    rows = []
    for yi, y in enumerate(years):
        for m in range(1, 13):
            rows.append({"year": y, "month": m, "revenue": 100.0 * (yi + 1) + m})
    return rows


def test_numeric_and_date_columns_split_year_month():
    s = summarize_rows(_monthly())
    assert s["rows"] == 36
    rev = s["measures"]["revenue"]
    assert set(s["measures"]) == {"revenue"}  # year/month are not measures
    assert rev["min"] == ["2020-01", 101]
    assert rev["max"] == ["2022-12", 312]
    assert rev["first"] == ["2020-01", 101]
    assert rev["last"] == ["2022-12", 312]
    assert rev["pct_change"] == round((312 - 101) / 101 * 100, 1)
    assert rev["by_year"] == {"2020": 1278, "2021": 2478, "2022": 3678}
    assert rev["total"] == 1278 + 2478 + 3678


def test_date_label_column_sorted_chronologically():
    rows = [{"month": f"2021-{m:02d}", "sales": m} for m in (3, 1, 2)]
    rows += [{"month": f"2020-{m:02d}", "sales": 10 * m} for m in (12, 11)]
    rev = summarize_rows(rows)["measures"]["sales"]
    assert rev["first"] == ["2020-11", 110]
    assert rev["last"] == ["2021-03", 3]
    assert rev["max"] == ["2020-12", 120]
    assert set(rev["by_year"]) == {"2020", "2021"}


def test_category_labels_have_no_time_stats():
    rows = [{"product": f"P{i}", "revenue": float(i), "units": i * 2} for i in range(1, 11)]
    s = summarize_rows(rows)["measures"]
    assert s["revenue"]["max"] == ["P10", 10]
    assert s["revenue"]["min"] == ["P1", 1]
    assert s["revenue"]["mean"] == 5.5
    assert s["units"]["total"] == 110
    assert "first" not in s["revenue"] and "by_year" not in s["revenue"]


def test_single_row():
    s = summarize_rows([{"product": "Monitor", "revenue": 688486.14}])
    m = s["measures"]["revenue"]
    assert s["rows"] == 1
    assert m["min"] == m["max"] == ["Monitor", 688486.14]
    assert "pct_change" not in m


def test_no_numeric_columns():
    s = summarize_rows([{"name": "a", "category": "x"}, {"name": "b", "category": "y"}])
    assert s == {"rows": 2, "measures": {}}


def test_empty():
    assert summarize_rows([]) == {"rows": 0, "measures": {}}


def test_nulls_ignored_and_counted():
    rows = [{"cat": c, "v": v} for c, v in zip("abcd", [5, None, 15, float("nan")])]
    m = summarize_rows(rows)["measures"]["v"]
    assert m["mean"] == 10 and m["total"] == 20
    assert m["min"] == ["a", 5] and m["max"] == ["c", 15]
    assert m["nulls"] == 2


def test_all_null_measure_skipped():
    s = summarize_rows([{"cat": "a", "v": None}, {"cat": "b", "v": None}])
    assert s["measures"] == {}


def test_id_columns_and_measure_cap():
    rows = [{"product_id": i, "a": i, "b": i, "c": i, "d": i} for i in range(1, 4)]
    assert list(summarize_rows(rows)["measures"]) == ["a", "b", "c"]


def test_zero_first_value_no_pct_change():
    rows = [{"month": "2020-01", "v": 0}, {"month": "2020-02", "v": 5}]
    assert "pct_change" not in summarize_rows(rows)["measures"]["v"]
