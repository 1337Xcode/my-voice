"""Batched dynamic time warping with cosine distance, a Sakoe-Chiba band and path-length normalisation."""

import torch
import torch.nn.functional as F

# Half-width of the band as a share of the longer sequence.
BAND_RATIO = 0.2
_BIG = float("inf")


def _band_halfwidth(a_len: torch.Tensor, b_len: torch.Tensor, band_ratio: float) -> tuple[torch.Tensor, torch.Tensor]:
    """Returns each pair's diagonal slope and band half-width (wide enough for a staircase path to reach the corner)."""
    slope = (b_len - 1).float() / (a_len - 1).clamp(min=1).float()
    steepest = torch.maximum(slope, 1.0 / slope.clamp(min=1e-3))
    longer = torch.maximum(a_len, b_len).float()
    half = torch.maximum(torch.ceil(band_ratio * longer), torch.ceil(steepest) + 1.0)
    return slope, torch.minimum(half, longer)


def _skewed_cost(cost: torch.Tensor, a_len: torch.Tensor, b_len: torch.Tensor, band_ratio: float) -> torch.Tensor:
    """Re-indexes the cost matrix by anti-diagonal: result[b, d, i] = cost[b, i, d - i], infinite outside the band."""
    batch, n, m = cost.shape
    device = cost.device
    diagonal = torch.arange(n + m - 1, device=device)[:, None]
    row = torch.arange(n, device=device)[None, :]
    col = diagonal - row
    in_matrix = (col >= 0) & (col < m)
    skewed = cost[:, row.expand_as(col), col.clamp(0, m - 1)]
    slope, half = _band_halfwidth(a_len, b_len, band_ratio)
    colf = col[None].float()
    inside = (colf - row[None].float() * slope[:, None, None]).abs() <= half[:, None, None]
    valid = in_matrix[None] & inside & (row[None] < a_len[:, None, None]) & (col[None] < b_len[:, None, None])
    return torch.where(valid, skewed, torch.full_like(skewed, _BIG))


@torch.inference_mode()
def dtw_batch(
    a: torch.Tensor, a_len: torch.Tensor, b: torch.Tensor, b_len: torch.Tensor, band_ratio: float = BAND_RATIO
) -> torch.Tensor:
    """Path-normalised DTW cosine distance for each pair (a[k], b[k]); a and b are zero-padded unit-norm frames.

    Shapes: a [B, N, D], b [B, M, D], lengths [B]. Steps are right, down and diagonal; the cost is summed along the
    cheapest path inside the band and divided by that path's length. The DP sweeps anti-diagonals so every pair in
    the batch advances in one vectorised step per diagonal.
    """
    batch, n, _ = a.shape
    m = b.shape[1]
    cost = 1.0 - torch.bmm(a, b.transpose(1, 2))
    skewed = _skewed_cost(cost, a_len, b_len, band_ratio)
    # State has a leading pad column so "row i-1" is the slice [:, :-1] and "row i" is [:, 1:].
    prev_cost = torch.full((batch, n + 1), _BIG, device=a.device)
    prev2_cost = prev_cost
    prev_len = torch.zeros_like(prev_cost)
    prev2_len = prev_len
    end_row = (a_len - 1)[:, None]
    last_cost: list[torch.Tensor] = []
    last_len: list[torch.Tensor] = []
    for d in range(n + m - 1):
        if d == 0:
            best = torch.full((batch, n), _BIG, device=a.device)
            best[:, 0] = 0.0
            best_len = torch.zeros((batch, n), device=a.device)
        else:
            cand_cost = torch.stack((prev2_cost[:, :-1], prev_cost[:, 1:], prev_cost[:, :-1]))
            cand_len = torch.stack((prev2_len[:, :-1], prev_len[:, 1:], prev_len[:, :-1]))
            pick = cand_cost.argmin(dim=0, keepdim=True)
            best = cand_cost.gather(0, pick)[0]
            best_len = cand_len.gather(0, pick)[0]
        new_cost = skewed[:, d] + best
        new_len = best_len + 1.0
        last_cost.append(new_cost.gather(1, end_row)[:, 0])
        last_len.append(new_len.gather(1, end_row)[:, 0])
        prev2_cost, prev2_len = prev_cost, prev_len
        prev_cost = F.pad(new_cost, (1, 0), value=_BIG)
        prev_len = F.pad(new_len, (1, 0))
    end_diagonal = (a_len + b_len - 2)[:, None]
    total_cost = torch.stack(last_cost, dim=1).gather(1, end_diagonal)[:, 0]
    total_len = torch.stack(last_len, dim=1).gather(1, end_diagonal)[:, 0]
    return total_cost / total_len
