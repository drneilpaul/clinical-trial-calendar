"""
Profiling utilities for performance monitoring

Provides timing decorators that work both in Streamlit and standalone contexts.
"""
import time
import functools

def timeit(func):
    """
    Decorator to measure function execution time.
    
    Works in both Streamlit (uses st.session_state) and standalone (uses print) contexts.
    Logs timing with appropriate level based on duration.
    
    Usage:
        @timeit
        def my_function():
            # your code here
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        
        # Format timing message
        if elapsed > 5.0:
            emoji = '🐌'
            level = 'warning'
        elif elapsed > 1.0:
            emoji = '⏱️'
            level = 'info'
        else:
            emoji = '⚡'
            level = 'info'
        
        message = f"{emoji} PERFORMANCE: {func.__name__} took {elapsed:.2f}s"
        
        # Try to use log_activity if available (Streamlit context)
        try:
            from helpers import log_activity
            # Use 'warning' level for slow functions to make them more visible
            # Use 'info' for fast functions
            log_activity(message, level=level)
            # Also print to console for visibility
            print(f"[PERF] {message}")
        except (ImportError, AttributeError):
            # Fallback for non-Streamlit contexts (testing, debugging)
            print(f"[PERF] {message}")
        
        return result
    
    return wrapper

def profile_dataframe_operation(df, operation_name):
    """
    Context manager for profiling DataFrame operations.
    
    Usage:
        with profile_dataframe_operation(df, "groupby operation"):
            result = df.groupby('col').sum()
    """
    class DataFrameProfiler:
        def __init__(self, df, name):
            self.df = df
            self.name = name
            self.start_time = None
        
        def __enter__(self):
            self.start_time = time.time()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = time.time() - self.start_time
            message = f"⏱️ {self.name} on {len(self.df)} rows took {elapsed:.2f}s"
            
            try:
                from helpers import log_activity
                log_activity(message, level='info')
            except (ImportError, AttributeError):
                print(message)
            
            return False
    
    return DataFrameProfiler(df, operation_name)

