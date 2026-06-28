class ValidationError(RuntimeError):
    def __init__(self, error_msg):
        self.error_msg = error_msg
    
    def __repr__(self):
        return f"Error Message: {self.error_msg}."