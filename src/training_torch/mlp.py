"""sklearn-compatible PyTorch MLP regressor with Huber loss.

Drop-in replacement for sklearn MLPRegressor inside a Pipeline:
  Pipeline([("scaler", StandardScaler()), ("reg", TorchMLPRegressor(...))])

fit() accepts optional X_val / y_val for early stopping on a held-out set.
When seeds has more than one element, trains one independent network per seed
and averages predictions — cheap multi-seed ensemble.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from sklearn.base import BaseEstimator
from torch.utils.data import DataLoader, TensorDataset


class TorchMLPRegressor(BaseEstimator):
    """Multi-output MLP with Huber loss; sklearn predict() interface.

    Parameters
    ----------
    hidden_sizes : tuple of int
        Width of each hidden layer.
    norm : str
        "none" or "layer" — LayerNorm after each hidden linear.
    seeds : tuple of int, optional
        Independent training runs; predictions are averaged.  None uses (random_state,).
    alpha : float
        L2 weight decay.
    """

    def __init__(
        self,
        hidden_sizes: tuple[int, ...] = (64, 64),
        *,
        norm: str = "none",          # 'none' | 'layer'
        alpha: float = 1e-4,
        lr: float = 1e-3,
        max_epochs: int = 200,
        patience: int = 20,
        batch_size: int = 128,
        huber_delta: float = 15.0,
        random_state: int = 42,
        seeds: tuple[int, ...] | None = None,
        verbose: bool = True,
    ) -> None:
        self.hidden_sizes = hidden_sizes
        self.norm = norm
        self.alpha = alpha
        self.lr = lr
        self.max_epochs = max_epochs
        self.patience = patience
        self.batch_size = batch_size
        self.huber_delta = huber_delta
        self.random_state = random_state
        self.seeds = seeds
        self.verbose = verbose

    # ── architecture ──────────────────────────────────────────────────────────

    def _build_net(self, in_features: int, out_features: int) -> nn.Module:
        layers: list[nn.Module] = []
        prev = in_features
        for h in tuple(self.hidden_sizes):
            layers.append(nn.Linear(prev, h))
            if self.norm == "layer":
                layers.append(nn.LayerNorm(h))
            layers.append(nn.ReLU())
            prev = h
        layers.append(nn.Linear(prev, out_features))
        net = nn.Sequential(*layers)
        for m in net.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                nn.init.zeros_(m.bias)
        return net

    # ── training ──────────────────────────────────────────────────────────────

    def _train_one_seed(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: np.ndarray | None,
        y_val: np.ndarray | None,
        seed: int,
    ) -> nn.Module:
        torch.manual_seed(seed)
        n_samples, n_features = X.shape
        n_outputs = y.shape[1] if y.ndim > 1 else 1

        net = self._build_net(n_features, n_outputs)
        criterion = nn.HuberLoss(delta=float(self.huber_delta))
        optimizer = torch.optim.Adam(
            net.parameters(), lr=float(self.lr), weight_decay=float(self.alpha)
        )

        X_t = torch.as_tensor(X, dtype=torch.float32)
        y_t = torch.as_tensor(y if y.ndim > 1 else y[:, None], dtype=torch.float32)
        loader = DataLoader(
            TensorDataset(X_t, y_t),
            batch_size=self.batch_size,
            shuffle=True,
            generator=torch.Generator().manual_seed(seed),
        )

        has_val = X_val is not None and y_val is not None
        Xv = y_np = ss_tot = None
        yv_t = None
        if has_val:
            Xv = torch.as_tensor(X_val, dtype=torch.float32)
            y_np = y_val if y_val.ndim > 1 else y_val[:, None]
            yv_t = torch.as_tensor(y_np, dtype=torch.float32)
            ss_tot = float(np.sum((y_np - y_np.mean(axis=0)) ** 2))

        best_val_loss = float("inf")
        best_state: dict | None = None
        bad_epochs = 0

        for epoch in range(1, self.max_epochs + 1):
            net.train()
            total_loss = 0.0
            for xb, yb in loader:
                optimizer.zero_grad()
                loss = criterion(net(xb), yb)
                loss.backward()
                optimizer.step()
                total_loss += loss.item() * len(xb)
            train_loss = total_loss / n_samples

            if has_val:
                net.eval()
                with torch.no_grad():
                    pred_v = self._forward_one(net, Xv)
                val_loss = criterion(pred_v, yv_t).item()
                if self.verbose:
                    ss_res = float(np.sum((y_np - pred_v.numpy()) ** 2))
                    val_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
                    marker = ""
                    if val_loss < best_val_loss - 1e-6:
                        marker = "  *"
                    print(
                        f"  [seed {seed}] epoch {epoch:3d}/{self.max_epochs}  "
                        f"train={train_loss:.4f}  val={val_loss:.4f}  "
                        f"R²={val_r2:+.4f}  bad={bad_epochs:2d}{marker}",
                        flush=True,
                    )

                if val_loss < best_val_loss - 1e-6:
                    best_val_loss = val_loss
                    best_state = {k: v.clone() for k, v in net.state_dict().items()}
                    bad_epochs = 0
                else:
                    bad_epochs += 1

                if bad_epochs >= self.patience:
                    if self.verbose:
                        print(f"  [seed {seed}] early stop at epoch {epoch}", flush=True)
                    break
            elif self.verbose:
                print(f"  [seed {seed}] epoch {epoch:3d}/{self.max_epochs}  train={train_loss:.4f}", flush=True)

        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        return net

    @staticmethod
    @torch.no_grad()
    def _forward_one(net: nn.Module, X_t: torch.Tensor, batch_size: int = 4096) -> torch.Tensor:
        """Chunked forward pass through a single net — bounds peak activation memory."""
        net.eval()
        if X_t.shape[0] <= batch_size:
            return net(X_t)
        return torch.cat([net(X_t[i:i + batch_size]) for i in range(0, X_t.shape[0], batch_size)], 0)

    @torch.no_grad()
    def _forward_batched(self, X_t: torch.Tensor, batch_size: int = 4096) -> torch.Tensor:
        """Average chunked forward pass across all trained nets (ensemble prediction)."""
        outs = [self._forward_one(net, X_t, batch_size) for net in self.nets_]
        return torch.stack(outs, 0).mean(0)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> "TorchMLPRegressor":
        seeds = self.seeds if self.seeds is not None else (self.random_state,)
        n_seeds = len(seeds)
        self.nets_: list[nn.Module] = []
        for i, seed in enumerate(seeds):
            if n_seeds > 1 and self.verbose:
                print(f"\n--- seed {i + 1}/{n_seeds} (seed={seed}) ---", flush=True)
            net = self._train_one_seed(X, y, X_val, y_val, seed)
            self.nets_.append(net)
        self.net_ = self.nets_[0]  # backward-compat attribute
        return self

    # ── inference ─────────────────────────────────────────────────────────────

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not hasattr(self, "nets_"):
            raise RuntimeError("Call fit() first.")
        x = torch.as_tensor(np.asarray(X, dtype=np.float32))
        return self._forward_batched(x).numpy()
