"""Synthetic-only scored-evaluator trace candidate. No I/O or scientific driver.

Preserves pre-score confirmation warmup; reconstructs valid from contact;
handles static negatives and ineligible finite contacts separately. Horizons
are per frame. Production use still requires a new frozen bounded/streamed
driver, complete input/causality checks and independent scientific close.
"""
import numpy as np
EPS=1e-9
FIELDS=('TP','FP','ref_FP','support','negative_opportunities','ref_negative_opportunities')

def confirmed_hits(time,hits,confirmation,eps=EPS):
    starts=np.full(hits.shape[1],np.nan)
    last=np.full(hits.shape[1],-2,dtype=np.int64)
    confirmed=np.zeros_like(hits)
    for k,t in enumerate(time):
        active=hits[k]
        restarted=active & (last!=k-1)
        starts[restarted]=t; last[active]=k
        confirmed[k]=active & (t-starts>=confirmation-eps)
    return confirmed

def scored_trace(time,hits,contact,front_ignored,confirmation,horizons,score_start,score_end,eps=EPS):
    time=np.asarray(time,dtype=np.float64); hits=np.asarray(hits)
    contact=np.asarray(contact,dtype=np.float64); front=np.asarray(front_ignored)
    horizons=np.asarray(horizons,dtype=np.float64)
    if (time.ndim!=1 or hits.ndim!=2 or hits.dtype!=np.bool_ or len(time)!=len(hits)
        or contact.shape!=(hits.shape[1],) or front.shape!=contact.shape or front.dtype!=np.bool_
        or horizons.shape!=time.shape or not np.isfinite(time).all() or np.any(np.diff(time)<=0)
        or not np.isfinite(horizons).all() or np.any(horizons<2)
        or np.isinf(contact).any() or not np.isfinite([confirmation,score_start,score_end,eps]).all()
        or confirmation<0 or eps<0 or score_start>score_end):
        raise ValueError('Exact scored trace shape/dtype, increasing time and horizons>=2 required')
    confirmed=confirmed_hits(time,hits,confirmation,eps)
    finite=np.isfinite(contact); negative=~finite
    eligible=(~front)&finite&(contact>=score_start-eps)&(contact<=score_end+eps)
    started=time>=score_start-eps
    scoring=started&(time<=score_end+eps)
    before=contact[None,:]>=time[:,None]-eps
    support=before&(contact[None,:]<=time[:,None]+horizons[:,None]+eps)
    reference=before&(contact[None,:]<=time[:,None]+2+eps)
    def first(mask):
        out=np.full(hits.shape[1],np.nan)
        present=mask.any(axis=0)
        if present.any(): out[present]=time[np.argmax(mask[:,present],axis=0)]
        return out
    out={'raw':first(hits),'first':first(confirmed&started[:,None]),
        'valid':first(confirmed&started[:,None]&support)}
    allowed=(eligible|negative)[None,:]&(before|negative[None,:])
    scored_hits=confirmed&scoring[:,None]&allowed
    out['TP']=(scored_hits&support).sum(axis=0).astype(np.int32)
    out['FP']=(scored_hits&~support).sum(axis=0).astype(np.int32)
    out['ref_FP']=(scored_hits&~reference).sum(axis=0).astype(np.int32)
    out['support']=(scoring[:,None]&support&eligible[None,:]).sum(axis=0).astype(np.int32)
    out['negative_opportunities']=(scoring[:,None]&((eligible[None,:]&before&~support)|negative[None,:])).sum(axis=0).astype(np.int32)
    out['ref_negative_opportunities']=(scoring[:,None]&((eligible[None,:]&before&~reference)|negative[None,:])).sum(axis=0).astype(np.int32)
    frames=np.zeros((len(time),4),dtype=np.int32)
    for k,t in enumerate(time):
        if not scoring[k]: continue
        tp=int((scored_hits[k]&support[k]).sum()); fp=int((scored_hits[k]&~support[k]).sum())
        support_n=int((eligible&support[k]).sum())
        noncontact_n=int(negative.sum()+(eligible&(contact>t+horizons[k]+eps)).sum())
        frames[k]=[tp,fp,noncontact_n-fp,support_n-tp]
    return out,confirmed,support,frames
