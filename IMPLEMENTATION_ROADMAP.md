# PortPulse ML Implementation Roadmap

**Current Status:** 60% ML-Based (September 18, 2026)  
**Target:** 95%+ ML-Based by Q4 2026

---

## Phase 1: Critical Gaps (Weeks 1-2) ⚠️

### 1.1 Implement Dynamic Weather-Based Reallocation (Priority 1)

**Problem:** Weather delays are static at plan time. No real-time monitoring or reallocation.

**Solution:**
```python
# NEW: src/portpulse/ml/weather_reallocator.py

class WeatherReallocator:
    def __init__(self, predictor, allocator, weather_monitor):
        self.predictor = predictor
        self.allocator = allocator
        self.weather = weather_monitor
        self.reallocation_history = []
    
    def monitor_and_reallocate(self, current_plan, check_interval_hours=4):
        """Monitor weather updates and trigger reallocation if beneficial."""
        while True:
            # Check for weather forecast updates
            weather_update = self.weather.fetch_updates()
            
            if self._should_reallocate(weather_update, current_plan):
                # Estimate new delays with updated weather
                new_delays = self.predictor.predict_route_delays(
                    vessels=current_plan.vessels,
                    forecast=weather_update
                )
                
                # Calculate cost delta
                old_cost = self._estimate_demurrage_cost(current_plan)
                new_plan = self.allocator.optimize(
                    vessels=current_plan.vessels,
                    weather_delays=new_delays
                )
                new_cost = self._estimate_demurrage_cost(new_plan)
                
                # Reallocate if cost reduced
                if new_cost < old_cost:
                    savings = old_cost - new_cost
                    logger.info(
                        f"Weather reallocation: ${savings:.2f} savings, "
                        f"{self._count_changes(current_plan, new_plan)} vessel reassignments"
                    )
                    current_plan = new_plan
                    self._notify_port_operators(new_plan, savings)
            
            # Sleep and check again
            await asyncio.sleep(check_interval_hours * 3600)
    
    def _should_reallocate(self, weather_update, current_plan):
        """ML-based decision: should we reallocate?"""
        for vessel in current_plan.vessels:
            old_severity = vessel.weather_severity
            new_severity = weather_update.get_severity_for_vessel(vessel.id)
            
            # Reallocate if severity changes significantly
            if self._severity_delta(old_severity, new_severity) > 1:
                return True
        
        return False
    
    def _severity_delta(self, old, new):
        """Quantify weather severity change."""
        severities = ['none', 'minor', 'moderate', 'severe']
        return abs(severities.index(new) - severities.index(old))
```

**Integration Points:**
- `src/portpulse/domain/planner.py` — Add reallocation trigger
- `src/portpulse/api/plan.py` — Add `/api/v1/reallocate` endpoint
- `src/portpulse/background_tasks.py` — Schedule reallocation monitor

**Testing:**
- Test weather forecast updates trigger reallocation correctly
- Verify cost delta calculation is accurate
- Test with 10+ synthetic weather scenarios
- Validate operator notifications

**Effort:** 3 days

---

### 1.2 Build ML Route Optimizer (Priority 1)

**Problem:** Routing is heuristic-only (distance + capacity fit). No ML optimization.

**Solution:**
```python
# NEW: src/portpulse/ml/route_optimizer.py

class RouteOptimizerML:
    def __init__(self, predictor):
        self.predictor = predictor
        self.route_model = None  # To be trained
        self.port_performance_db = {}  # Historical data
    
    def optimize_routes(self, unassigned_vessels, current_port, candidate_ports):
        """ML-based multi-objective route optimization."""
        optimized_routes = []
        
        for vessel in unassigned_vessels:
            # Generate candidate routes
            routes = self._generate_candidate_routes(
                vessel, 
                current_port, 
                candidate_ports
            )
            
            # Score each route using ML
            scored_routes = []
            for route in routes:
                score = self._score_route_ml(vessel, route)
                scored_routes.append((route, score))
            
            # Multi-objective optimization
            best_route = self._select_best_route(
                scored_routes,
                objectives={
                    'minimize_demurrage': 0.4,
                    'minimize_distance': 0.3,
                    'maximize_reliability': 0.3
                }
            )
            
            optimized_routes.append({
                'vessel_id': vessel.id,
                'route': best_route,
                'rationale': self._explain_route_choice(vessel, best_route)
            })
        
        return optimized_routes
    
    def _score_route_ml(self, vessel, route):
        """ML scoring using historical port performance."""
        alternate_port = route.destination
        
        # Features: vessel characteristics + port profile
        features = {
            'vessel_size_teu': vessel.size_teu,
            'cargo_type': vessel.cargo_type,
            'priority': vessel.priority,
            'distance_nm': route.distance,
            'alternate_port_capacity': alternate_port.capacity,
            'alternate_port_utilization': alternate_port.current_utilization,
            'alternate_port_avg_wait': self._get_port_stat(
                alternate_port.id, 
                'avg_wait_hours'
            ),
            'alternate_port_avg_dwell': self._get_port_stat(
                alternate_port.id, 
                'avg_dwell_hours'
            ),
            'alternate_port_reliability': self._get_port_stat(
                alternate_port.id, 
                'schedule_adherence'
            ),  # 0-1
            'alternate_port_success_rate': self._get_port_stat(
                alternate_port.id, 
                'cargo_success_rate'
            ),  # 0-1
            'vessel_size_fit': (
                alternate_port.capacity - vessel.size_teu
            ) / alternate_port.capacity,
        }
        
        # ML prediction
        demurrage_estimate = self.predictor.predict_demurrage_cost(features)
        distance_score = 100 - (route.distance / 10000 * 100)  # Normalize 0-100
        reliability_score = features['alternate_port_reliability'] * 100
        
        # Multi-objective score
        score = (
            (100 - demurrage_estimate/1000) * 0.4 +  # Minimize demurrage
            distance_score * 0.3 +                     # Minimize distance
            reliability_score * 0.3                    # Maximize reliability
        )
        
        return score
    
    def _get_port_stat(self, port_id, stat_name):
        """Retrieve historical port statistics."""
        if port_id not in self.port_performance_db:
            return self._fetch_port_performance(port_id)
        
        return self.port_performance_db[port_id].get(stat_name, 0)
```

**Integration:**
- `src/portpulse/domain/routing.py` — Replace `_rank_candidates()` with ML optimizer
- Database: Store historical port performance (`port_performance` table)
- API: `/api/v1/route-optimization` endpoint

**Model Training Data:**
- Historical alternate port performance
- Vessel characteristics that lead to successful routes
- Cargo type preferences per port
- Estimated dataset size: 10,000+ historical routing decisions

**Testing:**
- Test multi-objective scoring (demurrage vs. distance vs. reliability)
- Validate against known optimal routes
- Benchmark against heuristic approach
- A/B test with real port data (if available)

**Effort:** 4 days

---

## Phase 2: Model Integration & Optimization (Weeks 3-4) 🔧

### 2.1 Integrate Cascade Prediction ML Model (Quick Win)

**Problem:** Cascade prediction uses expensive iterative simulation. ML model exists but unused.

**Current Code (Inefficient):**
```python
# cascade_simulator.py lines 40-197
def simulate_cascade(disruption):
    for i in range(10):  # Iterate up to 10 times
        run_planner()  # Expensive re-planning each iteration
    return cumulative_delay
```

**Solution (ML-Based):**
```python
# In cascade_simulator.py
def predict_cascade_delay_ml(disruption_context):
    """Use ML instead of expensive iterative simulation."""
    features = {
        'initial_wait_hours': disruption_context.delay_hours,
        'n_vessels_queue': len(disruption_context.vessel_queue),
        'n_berths': len(disruption_context.berths),
        'avg_vessel_size': np.mean([v.size for v in disruption_context.vessel_queue]),
        'weather_severity': disruption_context.weather_severity,
        'priority_avg': np.mean([v.priority for v in disruption_context.vessel_queue]),
        'hour_of_day': datetime.now().hour,
        'utilization_ratio': disruption_context.utilization_ratio
    }
    
    # ML prediction (10ms) vs 5s for iterative simulation
    cascade_depth = predictor.predict_cascade_delay(features)
    cumulative_delay = cascade_depth * disruption_context.avg_vessel_size / 1000
    
    return {
        'cascade_depth': cascade_depth,
        'cumulative_delay_hours': cumulative_delay,
        'affected_vessel_count': int(cascade_depth * 0.5)
    }
```

**Performance:** 500x faster (5 seconds → 10 milliseconds)

**Effort:** 1-2 days

---

### 2.2 Add Iterative Berth Allocation Refinement

**Problem:** Single-pass allocation doesn't reoptimize over time.

**Solution:**
```python
# NEW: src/portpulse/domain/allocation_optimizer_iterative.py

class IterativeAllocationOptimizer:
    def __init__(self, allocator, max_iterations=5):
        self.allocator = allocator
        self.max_iterations = max_iterations
    
    def optimize_iteratively(self, vessels, berths, weather_context):
        """Refine allocation across multiple iterations."""
        plan = self.allocator.optimize(vessels, berths, weather_context)
        
        for iteration in range(self.max_iterations):
            # Identify suboptimal assignments
            suboptimal = self._find_suboptimal_assignments(plan)
            
            if not suboptimal:
                logger.info(f"Converged after {iteration} iterations")
                break
            
            # Re-optimize suboptimal vessels
            reassigned = self.allocator.optimize(
                vessels=[v for v, b in suboptimal],
                berths=berths,
                weather_context=weather_context,
                exclude_berths=[b for v, b in suboptimal]  # Try different berths
            )
            
            plan = self._merge_plans(plan, reassigned)
        
        return plan
    
    def _find_suboptimal_assignments(self, plan):
        """Identify vessels with poor wait/dwell balance."""
        suboptimal = []
        
        for assignment in plan.assignments:
            wait_ratio = assignment.wait_hours / (assignment.wait_hours + assignment.dwell_hours)
            
            # Flag if wait > 30% of total time
            if wait_ratio > 0.3:
                suboptimal.append((assignment.vessel, assignment.berth))
        
        return suboptimal
```

**Benefit:** Better berth utilization, 5-10% reduction in average wait time

**Effort:** 2 days

---

## Phase 3: Data & Model Management (Weeks 5-6) 📊

### 3.1 Build Model Registry & Versioning

**Implementation:**
```python
# NEW: src/portpulse/ml/model_registry.py

class ModelRegistry:
    def __init__(self, db_connection):
        self.db = db_connection
    
    def register_model(self, model_name, model_file, metrics, features, training_date):
        """Register trained model with metadata."""
        record = {
            'model_name': model_name,
            'version': self._get_next_version(model_name),
            'file_path': model_file,
            'status': 'active',  # or 'archived', 'testing'
            'accuracy': metrics.get('accuracy'),
            'r2_score': metrics.get('r2_score'),
            'rmse': metrics.get('rmse'),
            'training_samples': metrics.get('training_samples'),
            'training_date': training_date,
            'features': features,
            'last_retraining': datetime.now()
        }
        self.db.insert('model_registry', record)
    
    def load_model(self, model_name, version='latest'):
        """Load specific model version."""
        record = self.db.query_one(
            'model_registry',
            model_name=model_name,
            version=version
        )
        return joblib.load(record['file_path'])
    
    def compare_models(self, model_name, versions):
        """Compare performance across model versions."""
        records = self.db.query(
            'model_registry',
            model_name=model_name,
            version__in=versions
        )
        return sorted(records, key=lambda x: x['r2_score'], reverse=True)
    
    def enable_ab_test(self, model_name_a, model_name_b, traffic_split=0.5):
        """A/B test two model versions."""
        self.db.insert('ab_tests', {
            'model_a': model_name_a,
            'model_b': model_name_b,
            'traffic_split': traffic_split,
            'start_date': datetime.now(),
            'status': 'active'
        })
```

**Database Schema:**
```sql
CREATE TABLE model_registry (
  id INT PRIMARY KEY AUTO_INCREMENT,
  model_name VARCHAR(100),
  version INT,
  file_path VARCHAR(255),
  status VARCHAR(20),
  accuracy FLOAT,
  r2_score FLOAT,
  rmse FLOAT,
  training_samples INT,
  training_date DATETIME,
  features JSON,
  last_retraining DATETIME,
  UNIQUE(model_name, version)
);

CREATE TABLE ab_tests (
  id INT PRIMARY KEY AUTO_INCREMENT,
  model_a VARCHAR(100),
  model_b VARCHAR(100),
  traffic_split FLOAT,
  start_date DATETIME,
  status VARCHAR(20)
);
```

**Effort:** 2-3 days

---

### 3.2 Replace Synthetic Data with Real Historical Data

**Current Problem:**
- All 9 models trained on 50K synthetic samples
- No validation against real port operations
- Models may not generalize to actual patterns

**Solution:**
1. **Data Collection Phase:**
   - Extract historical vessel arrivals, assignments, actual dwell times from MySQL
   - Validate data quality (remove outliers, handle missing values)
   - Target: 10,000+ historical operations per model

2. **Data Pipeline:**
```python
# NEW: src/portpulse/ml/data_pipeline.py

class PortPulseDataPipeline:
    def __init__(self, db_connection):
        self.db = db_connection
    
    def prepare_training_data(self, model_name, lookback_days=365):
        """Prepare real historical data for model retraining."""
        
        if model_name == 'wait_time_model':
            data = self._prepare_wait_time_data(lookback_days)
        elif model_name == 'dwell_time_model':
            data = self._prepare_dwell_time_data(lookback_days)
        elif model_name == 'risk_model':
            data = self._prepare_risk_data(lookback_days)
        # ... other models
        
        # Data validation
        data = self._validate_data(data)
        
        # Feature engineering
        features = self._engineer_features(data)
        
        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            features, 
            data['target'], 
            test_size=0.2
        )
        
        return X_train, X_test, y_train, y_test
    
    def _prepare_wait_time_data(self, lookback_days):
        """Extract wait time history."""
        query = f"""
        SELECT 
            v.size_teu,
            v.priority,
            v.cargo_type,
            b.crane_count,
            (a.berth_start - v.eta) as wait_hours,
            c.wave_height_m,
            c.weather_severity,
            HOUR(a.berth_start) as hour_of_day,
            DAYOFWEEK(a.berth_start) as day_of_week
        FROM assignments a
        JOIN vessels v ON a.vessel_id = v.id
        JOIN berths b ON a.berth_id = b.id
        LEFT JOIN weather_context c ON a.id = c.assignment_id
        WHERE a.created_at > DATE_SUB(NOW(), INTERVAL {lookback_days} DAY)
        """
        return pd.read_sql(query, self.db)
```

**Retraining Schedule:**
- Weekly: Retrain with last 7 days of data
- Monthly: Full retraining with last 365 days
- Quarterly: Model selection and architecture tuning

**Effort:** 3-4 days (plus ongoing data collection)

---

## Phase 4: Monitoring & Continuous Improvement (Weeks 7-8) 📈

### 4.1 Build Model Performance Monitoring Dashboard

```python
# NEW: src/portpulse/monitoring/model_monitor.py

class ModelPerformanceMonitor:
    def __init__(self, db_connection):
        self.db = db_connection
        self.metrics = {}
    
    def track_prediction(self, model_name, features, prediction, actual=None):
        """Track individual predictions for monitoring."""
        self.db.insert('prediction_log', {
            'model_name': model_name,
            'timestamp': datetime.now(),
            'features_hash': hash(str(features)),
            'prediction': prediction,
            'actual': actual,
            'error': abs(prediction - actual) if actual else None
        })
    
    def calculate_performance_metrics(self, model_name, window_days=7):
        """Calculate accuracy metrics over time window."""
        predictions = self.db.query(
            'prediction_log',
            model_name=model_name,
            timestamp__gte=datetime.now() - timedelta(days=window_days)
        )
        
        errors = [p['error'] for p in predictions if p['error']]
        
        return {
            'mae': np.mean(errors),
            'rmse': np.sqrt(np.mean(np.square(errors))),
            'median_error': np.median(errors),
            'prediction_count': len(predictions),
            'actual_available_rate': len([p for p in predictions if p['actual']]) / len(predictions)
        }
    
    def detect_model_drift(self, model_name, threshold=0.15):
        """Detect if model performance degrading (drift detection)."""
        current_metrics = self.calculate_performance_metrics(model_name, 7)
        baseline_metrics = self.calculate_performance_metrics(model_name, 60)
        
        mae_degradation = (
            (current_metrics['mae'] - baseline_metrics['mae']) / 
            baseline_metrics['mae']
        )
        
        if mae_degradation > threshold:
            logger.warning(
                f"Model drift detected: {model_name} MAE degraded {mae_degradation:.1%}"
            )
            return True
        
        return False
    
    def recommend_retraining(self, model_name):
        """Recommend retraining if drift detected."""
        if self.detect_model_drift(model_name):
            return {
                'action': 'RETRAIN',
                'model_name': model_name,
                'reason': 'Performance degradation detected',
                'recommended_date': datetime.now() + timedelta(days=1)
            }
        
        return None
```

**Dashboard Metrics:**
- Model accuracy over time (7d, 30d, 90d)
- Prediction error distribution
- Drift detection alerts
- Data quality metrics

**Effort:** 2-3 days

---

## Implementation Timeline

| Phase | Duration | Effort | Completion |
|-------|----------|--------|------------|
| **Phase 1: Critical Gaps** | 2 weeks | 10 days | 70% ML-based |
| **Phase 2: Integration** | 2 weeks | 5 days | 80% ML-based |
| **Phase 3: Management** | 2 weeks | 7 days | 85% ML-based |
| **Phase 4: Monitoring** | 2 weeks | 5 days | **95%+ ML-based** |
| **Total** | **8 weeks** | **27 days** | **Complete** |

---

## Success Metrics

By end of Phase 4, PortPulse should achieve:

| Metric | Target |
|--------|--------|
| ML-based Features | 95%+ |
| Average Wait Time | -15% vs current |
| Berth Utilization | +12% vs current |
| Demurrage Cost Prediction | R² > 0.95 |
| Route Optimization Savings | $50K-100K/month (est) |
| Weather Reallocation Decisions | 50+ per month |
| Model Drift Detection | < 2% monthly |
| Prediction Latency | < 100ms (95th %ile) |

---

## Resource Requirements

- **Team:** 2 ML engineers + 1 backend engineer
- **Infrastructure:** GPU optional (for training), not required (inference on CPU)
- **Data:** Historical 365 days of port operations (ongoing)
- **Budget:** Model hosting + API calls + monitoring tools

