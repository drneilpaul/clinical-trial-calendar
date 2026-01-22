# Performance Optimization Analysis

## Current Performance: 5.80s for calendar build

### Timing Breakdown (from @timeit decorators):
- `_build_calendar_cached`: 5.80s (overall)
- `_build_calendar_impl`: 5.80s (main orchestrator)
- `process_all_patients`: ~4-5s (estimated, most expensive)
- `build_calendar_dataframe`: <1s
- `fill_calendar_with_visits`: <1s
- `calculate_financial_totals`: <0.5s

### Current Optimizations Already in Place:
✅ Uses `itertuples()` instead of `iterrows()` (2-3x faster)
✅ Vectorized financial calculations with `groupby().cumsum()`
✅ Streamlit caching with `@st.cache_data`
✅ Performance monitoring with `@timeit` decorator

### Bottleneck: process_all_patients (processing_calendar.py:522-585)

**Current approach:**
```python
for patient_tuple in patients_df.itertuples():
    # Convert tuple to dict
    patient = {...}

    # Call process_single_patient for each patient
    visit_records, ... = process_single_patient(patient, ...)

    # Accumulate results
    all_visit_records.extend(visit_records)
```

**Why it's slow:**
1. Sequential processing - processes one patient at a time
2. Each `process_single_patient` call:
   - Filters visits by study/pathway
   - Loops over study_visits using `itertuples()`
   - Calculates tolerance windows for each visit
   - Matches actual visits
   - Creates visit records individually

3. For N patients × M visits, this is O(N × M) operations without vectorization

## Optimization Strategies

### Option 1: Vectorized Visit Generation (Recommended)
**Impact: 50-70% reduction (2.90s - 1.74s)**

Replace patient-by-patient processing with vectorized operations:

```python
# Instead of looping over patients, do bulk operations:
# 1. Cross-join patients with trial_schedules by Study+Pathway
# 2. Vectorized date calculations (screening_date + visit_day)
# 3. Bulk tolerance window calculations
# 4. Vectorized actual visit matching using merge operations

merged = patients_df.merge(
    trial_schedules,
    on=['Study', 'Pathway'],
    how='inner'
)

# Vectorized date calculation
merged['ExpectedDate'] = merged['ScreeningDate'] + pd.to_timedelta(merged['Day'], unit='D')

# Vectorized tolerance windows
merged['WindowStart'] = merged['ExpectedDate'] - pd.to_timedelta(merged['ToleranceBefore'], unit='D')
merged['WindowEnd'] = merged['ExpectedDate'] + pd.to_timedelta(merged['ToleranceAfter'], unit='D')

# Bulk match actual visits using merge
visit_records = merged.merge(
    actual_visits,
    left_on=['PatientID', 'Study', 'VisitName'],
    right_on=['PatientID', 'Study', 'VisitName'],
    how='left',
    indicator=True
)
```

**Pros:**
- Leverages pandas vectorization (C-optimized)
- Eliminates Python loops
- ~3x faster for typical datasets

**Cons:**
- More complex logic for special cases (proposed visits, screen failures)
- Harder to debug
- Requires careful handling of edge cases

### Option 2: Parallel Processing with multiprocessing
**Impact: 30-50% reduction (4.06s - 2.90s) on multi-core systems**

Process patients in parallel using Python's multiprocessing:

```python
from multiprocessing import Pool
import os

def process_patient_chunk(chunk_data):
    patients_chunk, patient_visits, stoppages, actual_visits_df = chunk_data
    results = []
    for patient_tuple in patients_chunk.itertuples():
        result = process_single_patient(...)
        results.append(result)
    return results

# Split patients into chunks (one per CPU core)
num_cores = os.cpu_count()
chunks = np.array_split(patients_df, num_cores)

with Pool(num_cores) as pool:
    chunk_results = pool.map(process_patient_chunk, chunk_data)
```

**Pros:**
- Minimal code changes
- Easy to implement
- Scales with CPU cores

**Cons:**
- Overhead of process creation
- Not helpful if dataset is small
- Streamlit Cloud might have CPU limits

### Option 3: Reduce Repeated Operations
**Impact: 10-20% reduction (5.22s - 4.64s)**

Cache and pre-compute frequently used values:

```python
# Pre-filter visits by study once
study_visit_cache = {}
for study in patients_df['Study'].unique():
    study_visit_cache[study] = {
        pathway: patient_visits[(patient_visits['Study'] == study) &
                               (patient_visits['Pathway'] == pathway)]
        for pathway in patient_visits[patient_visits['Study'] == study]['Pathway'].unique()
    }

# Then in loop:
study_visits = study_visit_cache[study][pathway]  # O(1) lookup instead of filter
```

**Pros:**
- Easy to implement
- No architectural changes
- Safe and incremental

**Cons:**
- Limited impact
- Only helps if lots of duplicate filtering

### Option 4: Lazy Loading and Pagination
**Impact: Perceived performance improvement**

Load calendar in chunks or show partial results:

```python
# Process only visible date range first
today = pd.Timestamp.today()
priority_range = (today - timedelta(days=30), today + timedelta(days=90))

# Process priority range first, show to user
# Process rest in background
```

**Pros:**
- User sees results faster
- Better UX

**Cons:**
- Doesn't reduce total processing time
- More complex state management

## Recommended Approach

**Phase 1 (Quick Win - 10-20% improvement):**
1. Implement Option 3: Pre-compute study/pathway visit filters
2. Add more specific timing to identify exact bottleneck
3. Profile with actual dataset to validate assumptions

**Phase 2 (Major Optimization - 50-70% improvement):**
1. Implement Option 1: Vectorized visit generation
2. Start with core visit calculation
3. Incrementally handle edge cases (proposed visits, screen failures)

**Phase 3 (If needed - 30-50% additional):**
1. Add parallel processing for very large datasets
2. Only if Phase 1+2 don't achieve target performance

## Implementation Priority

### Immediate (Low Risk):
- [x] Add detailed timing breakdowns
- [ ] Pre-compute study/pathway filters (Option 3)
- [ ] Profile actual visit matching separately

### Next (Medium Risk):
- [ ] Vectorize core visit generation (Option 1)
- [ ] Benchmark against current implementation
- [ ] Validate edge cases

### Future (If Needed):
- [ ] Add parallel processing (Option 2)
- [ ] Implement lazy loading (Option 4)

## Performance Target

- Current: 5.80s
- Target: <2.00s (65% reduction)
- Stretch goal: <1.00s (83% reduction)

## Measurement Plan

Add granular timing:
```python
@timeit
def generate_predicted_visits(patients_df, trial_schedules):
    """Isolate predicted visit generation"""
    pass

@timeit
def match_actual_visits(predicted_visits, actual_visits):
    """Isolate actual visit matching"""
    pass
```

Then compare before/after optimization.
