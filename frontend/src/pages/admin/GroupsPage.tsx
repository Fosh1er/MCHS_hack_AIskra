/** Группы обучающихся (п. 5.2): состав с ролью на занятиях и профилем ДДС. Преподаватель назначает занятие группой. */
import { useMemo, useState } from 'react';
import { Banner, Button, Card } from '@smena112/ui-kit';
import { useServices } from '../../shared/api/dictionaries';
import { useDeleteGroup, useGroups, useSaveGroup, useUsers, type Group, type GroupMember } from '../../shared/api/admin';
import { CabinetShell } from '../../shared/ui/CabinetShell';

function Editor({ group, onClose }: { group: Group | null; onClose: () => void }) {
  const students = useUsers({ q: '', role: 'student', status: 'active', page: 1 });
  const services = useServices();
  const save = useSaveGroup();
  const del = useDeleteGroup();
  const [name, setName] = useState(group?.name ?? '');
  const [members, setMembers] = useState<Record<string, GroupMember>>(Object.fromEntries((group?.members ?? []).map((m) => [m.user_id, m])));
  const svc = useMemo(() => [...(services.data ?? [])].sort((a, b) => Number(b.kind === 'emergency') - Number(a.kind === 'emergency')), [services.data]);
  const toggle = (id: string) => setMembers((m) => { const n = { ...m }; if (n[id]) delete n[id]; else n[id] = { user_id: id, member_role: '112', dds_service_code: null }; return n; });
  const patch = (id: string, p: Partial<GroupMember>) => setMembers((m) => ({ ...m, [id]: { ...m[id], ...p } }));
  const list = Object.values(members);
  const missing = list.some((m) => m.member_role === 'dds' && !m.dds_service_code);
  return (
    <Card title={group ? `Группа «${group.name}»` : 'Новая группа'}>
      <div className="tch-form"><label>Название<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: 112-весна-1" /></label></div>
      <table className="cab-table" style={{ marginTop: 8 }}>
        <thead><tr><th /><th>Обучающийся</th><th>Роль на занятиях</th><th>Служба (для ДДС)</th></tr></thead>
        <tbody>
          {students.data?.items.map((s) => {
            const m = members[s.id];
            return (
              <tr key={s.id}>
                <td><input type="checkbox" aria-label={`В группе: ${s.full_name}`} checked={!!m} onChange={() => toggle(s.id)} /></td>
                <td>{s.full_name} <small className="c-slate">{s.login}</small></td>
                <td>{m && (
                  <select className="cab-select" aria-label={`Роль: ${s.full_name}`} value={m.member_role} onChange={(e) => patch(s.id, { member_role: e.target.value as '112' | 'dds' })}>
                    <option value="112">оператор 112</option><option value="dds">диспетчер ДДС</option>
                  </select>
                )}</td>
                <td>{m?.member_role === 'dds' && (
                  <select className="cab-select" aria-label={`Служба: ${s.full_name}`} value={m.dds_service_code ?? ''} onChange={(e) => patch(s.id, { dds_service_code: e.target.value || null })}>
                    <option value="">выберите службу</option>
                    {svc.map((d) => <option key={d.code} value={d.code}>{d.short}</option>)}
                  </select>
                )}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="cab-filters" style={{ marginTop: 10 }}>
        <Button variant="primary" icon="save" disabled={save.isPending || name.trim().length < 2 || missing}
          onClick={() => save.mutate({ id: group?.id, name: name.trim(), members: list }, { onSuccess: onClose })}>сохранить</Button>
        <Button variant="ghost" onClick={onClose}>отмена</Button>
        {group && <Button variant="danger" icon="close" disabled={del.isPending} onClick={() => del.mutate(group.id, { onSuccess: onClose })}>удалить группу</Button>}
        <span className="cab-filters__label">в группе: {list.length}{missing ? ' · укажите службу для ДДС' : ''}</span>
      </div>
      {(save.error ?? del.error) && <Banner status="critical">{(save.error ?? del.error)!.message}</Banner>}
    </Card>
  );
}

export function GroupsPage() {
  const groups = useGroups();
  const services = useServices();
  const names = new Map((services.data ?? []).map((s) => [s.code, s.short]));
  const [editing, setEditing] = useState<Group | 'new' | null>(null);
  return (
    <CabinetShell kind="admin" active="groups" title="Группы обучающихся"
      actions={!editing && <Button variant="primary" icon="plus" onClick={() => setEditing('new')}>группа</Button>}>
      {editing && <Editor key={editing === 'new' ? 'new' : editing.id} group={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      <Card flush>
        <table className="cab-table">
          <thead><tr><th>Группа</th><th className="num">Участников</th><th>Состав</th></tr></thead>
          <tbody>
            {groups.data?.map((g) => (
              <tr key={g.id} style={{ cursor: 'pointer' }} onClick={() => setEditing(g)}>
                <td><b>{g.name}</b></td><td className="num">{g.members.length}</td>
                <td className="c-slate">{g.members.map((m) => `${m.full_name} (${m.member_role === 'dds' ? names.get(m.dds_service_code ?? '') ?? m.dds_service_code : '112'})`).join(', ')}</td>
              </tr>
            ))}
            {groups.data && !groups.data.length && <tr><td colSpan={3} className="c-slate">Групп пока нет.</td></tr>}
          </tbody>
        </table>
      </Card>
    </CabinetShell>
  );
}
