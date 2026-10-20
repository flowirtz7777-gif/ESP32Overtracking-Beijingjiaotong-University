function summary=summarize_contact_edges(tbl)
%SUMMARIZE_CONTACT_EDGES Diagnose scope without calling all-body misses right-side misses.
    edges=unique(string(tbl.nearest_contact_edge));
    total=zeros(numel(edges),1); eligible=total; late=total; miss=total; sufficient=total; ignored=total;
    for i=1:numel(edges)
        selected=string(tbl.nearest_contact_edge)==edges(i);
        event=string(tbl.event(selected)); total(i)=nnz(selected);
        late(i)=nnz(event=="BLINDSPOT_REACTION_INSUFFICIENT");
        miss(i)=nnz(event=="POLYW_NO_HIT"); sufficient(i)=nnz(event=="REACTION_TIME_SUFFICIENT");
        eligible(i)=late(i)+miss(i)+sufficient(i);
        ignored(i)=nnz(event=="FRONT_CONTACT_IGNORED");
    end
    insufficient_rate=(late+miss)./eligible;
    summary=table(edges,total,eligible,late,miss,sufficient,insufficient_rate,ignored, ...
        'VariableNames',{'nearest_contact_edge','total','eligible_positive','late_count', ...
        'miss_count','sufficient_count','insufficient_rate','front_ignored_count'});
end
