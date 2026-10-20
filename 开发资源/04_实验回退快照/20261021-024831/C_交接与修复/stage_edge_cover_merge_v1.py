"""Code-only future merge preparation; never reads candidate data or invokes research."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
STAGE=HERE/'edge_cover_merge_staging_v1'


def main():
    if STAGE.exists(): raise RuntimeError('Preserve staged version')
    text=(HERE/'suffix_full_merge_staging_v1/suffix_merge_core.py').read_text(encoding='utf-8')
    a=text.index('MUTABLE = '); b=text.index('\nPREFIXES',a)
    text=text[:a]+"MUTABLE = {'edge_certain','possible_edge_codes'}"+text[b:]
    text=text.replace("'suffix_merge_')","'suffix_merge_', 'edge_cover_merge_')")
    a=text.index('\ndef merge_path(')+1; b=text.index('\ndef changed(',a)
    text=text[:a]+'''def merge_path(original,index,candidate,full_scope,found,*,scalar=False):
    n=len(original['contact_status'])
    if (full_scope.dtype!=np.bool_ or full_scope.shape!=(n,)
        or index.ndim!=1 or index.dtype.kind!='i' or index.dtype.itemsize not in (4,8)
        or not np.array_equal(index,np.flatnonzero(full_scope))
        or set(candidate)!=set(original) or found.dtype!=np.bool_ or found.shape!=(len(index),)):
        raise ValueError('Every complete original scope row and signed index required')
    old={k:take(v,index,scalar=scalar) for k,v in original.items()}
    eligible=np.isfinite(old['contact_lower_s'])&np.isfinite(old['contact_upper_s'])&(old['contact_status']==1)&~old['edge_certain']
    if np.any(found&~eligible): raise ValueError('Only originally witnessed uncertain edges may gain cover certificates')
    for key,value in original.items():
        new=candidate[key]
        if new.dtype!=value.dtype or new.shape!=(len(index),)+value.shape[1:]:
            raise ValueError('Every field dtype and full shape required')
        if key not in MUTABLE and not same(new,old[key]):
            raise ValueError('Scientific endpoints/contact/nominal/provenance changed')
        if not same(new[~found],old[key][~found]):
            raise ValueError('Every uncertified unknown/known row must remain byte-exact')
    nominal=old['nominal_instantaneous_edge'][found].astype(np.int64)
    if (np.any((nominal<1)|(nominal>8)) or not candidate['edge_certain'][found].all()
        or np.any(candidate['possible_edge_codes'][found].astype(np.int64)!=np.left_shift(1,nominal-1))):
        raise ValueError('Complete cover certificates require the original nominal singleton')
    out={}
    for key,value in original.items():
        result=value.copy()
        if scalar:
            for j,i in enumerate(index): result[int(i)]=candidate[key][j]
        else: result[index]=candidate[key]
        if not same(result[~full_scope],value[~full_scope]) or not same(result[index],candidate[key]):
            raise ValueError('Full selected and unselected bytes differ')
        out[key]=result
    return out

''' + text[b:]
    text=text.replace("out['suffix_merge_' + kind", "out['edge_cover_merge_' + kind")
    text=text.replace("('new_witness', witness_mask)","('certified', witness_mask)")
    text=text.replace('new-witness rows','newly certified edge rows')
    compile(text,'edge_merge_core.py','exec')
    STAGE.mkdir()
    (STAGE/'edge_merge_core.py').write_bytes(text.encode('utf-8'))
    print('FUTURE EDGE COVER MERGE PURE CORE STAGED; NO DATA/HASH BINDING/FREEZE/PREPARE/RUN')


if __name__=='__main__': main()
