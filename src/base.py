"""
Base Transformer Classes for PAR Data Pipeline

Provides sklearn-style transformer base classes for data processing steps.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
import pandas as pd
from pathlib import Path
import logging


class BaseTransformer(ABC):
    """Base class for all pipeline transformers."""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        """Initialize transformer with name and configuration."""
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"pipeline.{name}")
        self._fitted = False
    
    @abstractmethod
    def fit(self, df: pd.DataFrame, **kwargs) -> 'BaseTransformer':
        """Fit the transformer to the data."""
        pass
    
    @abstractmethod
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Transform the data."""
        pass
    
    def fit_transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Fit and transform in one step."""
        return self.fit(df, **kwargs).transform(df, **kwargs)
    
    def is_fitted(self) -> bool:
        """Check if transformer has been fitted."""
        return self._fitted
    
    def get_params(self) -> Dict[str, Any]:
        """Get transformer parameters."""
        return self.config.copy()
    
    def set_params(self, **params):
        """Set transformer parameters."""
        self.config.update(params)
        return self


class BaseReferenceExtractor(BaseTransformer):
    """Base class for extracting references from external files."""
    
    def __init__(self, name: str, source_file: str, config: Dict[str, Any] = None):
        """Initialize with source file path."""
        super().__init__(name, config)
        self.source_file = Path(source_file)
        self.references: Set[str] = set()
    
    @abstractmethod
    def extract_references(self) -> Set[str]:
        """Extract references from the source file."""
        pass
    
    def fit(self, df: pd.DataFrame, **kwargs) -> 'BaseReferenceExtractor':
        """Fit by extracting references from source file."""
        self.logger.info(f"Extracting references from {self.source_file}")
        
        if not self.source_file.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_file}")
        
        self.references = self.extract_references()
        self.logger.info(f"Extracted {len(self.references)} references")
        self._fitted = True
        return self
    
    def get_references(self) -> Set[str]:
        """Get extracted references."""
        if not self._fitted:
            raise ValueError("Must call fit() before accessing references")
        return self.references.copy()


class BaseReconciler(BaseTransformer):
    """Base class for reconciliation transformers."""
    
    def __init__(self, 
                 name: str,
                 target_column: str,
                 reference_extractor: BaseReferenceExtractor,
                 config: Dict[str, Any] = None):
        """Initialize reconciler with target column and reference extractor."""
        super().__init__(name, config)
        self.target_column = target_column
        self.reference_extractor = reference_extractor
        self.reference_column = config.get('reference_column', 'TNA_Reference')
    
    def fit(self, df: pd.DataFrame, **kwargs) -> 'BaseReconciler':
        """Fit by preparing reference extractor."""
        self.logger.info(f"Fitting reconciler for column: {self.target_column}")
        
        # Ensure reference extractor is fitted
        if not self.reference_extractor.is_fitted():
            self.reference_extractor.fit(df, **kwargs)
        
        self._fitted = True
        return self
    
    @abstractmethod
    def reconcile_references(self, df: pd.DataFrame) -> pd.DataFrame:
        """Perform the actual reconciliation logic."""
        pass
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Transform by performing reconciliation."""
        if not self._fitted:
            raise ValueError("Must call fit() before transform()")
        
        self.logger.info(f"Reconciling {len(df)} records for {self.target_column}")
        
        # Check if target column exists, create if not
        if self.target_column not in df.columns:
            df[self.target_column] = None
            self.logger.info(f"Created new column: {self.target_column}")
        
        # Perform reconciliation
        result_df = self.reconcile_references(df.copy())
        
        # Log statistics
        if self.target_column in result_df.columns:
            value_counts = result_df[self.target_column].value_counts()
            self.logger.info(f"Reconciliation results: {dict(value_counts)}")
        
        return result_df


class TransformationPipeline:
    """Pipeline for chaining multiple transformers."""
    
    def __init__(self, name: str = "pipeline"):
        """Initialize empty pipeline."""
        self.name = name
        self.steps: List[BaseTransformer] = []
        self.logger = logging.getLogger(f"pipeline.{name}")
    
    def add_step(self, transformer: BaseTransformer) -> 'TransformationPipeline':
        """Add a transformer to the pipeline."""
        self.steps.append(transformer)
        self.logger.info(f"Added step: {transformer.name}")
        return self
    
    def fit(self, df: pd.DataFrame, **kwargs) -> 'TransformationPipeline':
        """Fit all transformers in sequence."""
        self.logger.info(f"Fitting pipeline with {len(self.steps)} steps")
        
        current_df = df
        for step in self.steps:
            self.logger.info(f"Fitting step: {step.name}")
            step.fit(current_df, **kwargs)
            
        return self
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Transform data through all steps."""
        self.logger.info(f"Transforming data through {len(self.steps)} steps")
        
        current_df = df
        for step in self.steps:
            self.logger.info(f"Applying step: {step.name}")
            current_df = step.transform(current_df, **kwargs)
            
        return current_df
    
    def fit_transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Fit and transform in one step."""
        return self.fit(df, **kwargs).transform(df, **kwargs)
    
    def get_step(self, name: str) -> Optional[BaseTransformer]:
        """Get a transformer by name."""
        for step in self.steps:
            if step.name == name:
                return step
        return None
    
    def remove_step(self, name: str) -> bool:
        """Remove a transformer by name."""
        for i, step in enumerate(self.steps):
            if step.name == name:
                del self.steps[i]
                self.logger.info(f"Removed step: {name}")
                return True
        return False