"use client";

import { useEffect, useState } from "react";
import { RetentionSettings } from "../imports/retention";
import {
  api,
  ApiError,
  type AuditEvent,
  type Member,
  type Page,
} from "../../lib/api";
import {
  Field,
  messageFor,
  MutationForm,
  Pagination,
  TenantFrame,
  useTenant,
} from "../products/ui";

function Settings({ refresh }: { refresh: () => void }) {
  const tenant = useTenant();
  const org = tenant.organization.id;
  const owner = tenant.role === "owner";
  const manager = owner || tenant.role === "admin";
  const [members, setMembers] = useState<Page<Member> | null>(null);
  const [events, setEvents] = useState<Page<AuditEvent> | null>(null);
  const [page, setPage] = useState(1);
  const [auditPage, setAuditPage] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!tenant.organization.is_active) return;
    let live = true;
    void api
      .members(org, page)
      .then((value) => {
        if (live) setMembers(value);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [org, page, tenant.organization.is_active]);
  useEffect(() => {
    if (!manager || !tenant.organization.is_active) return;
    let live = true;
    void api
      .audit(org, auditPage)
      .then((value) => {
        if (live) setEvents(value);
      })
      .catch((failure) => {
        if (live) setError(messageFor(failure));
      });
    return () => {
      live = false;
    };
  }, [org, auditPage, manager, tenant.organization.is_active]);
  if (!tenant.organization.is_active)
    return (
      <>
        <h1>Organization settings</h1>
        <p>This organization is suspended. Only its owner can reactivate it.</p>
        {owner && (
          <MutationForm
            label="Reactivate organization"
            action={async () => {
              await api.setOrganizationActive(org, true);
              refresh();
            }}
          >
            <p>
              Reactivate access for current members. Existing permissions and
              plan limits continue to apply.
            </p>
          </MutationForm>
        )}
      </>
    );
  return (
    <>
      <h1>Organization settings</h1>
      <p>
        Access changes take effect on the server. Adding an existing registered
        username grants access immediately; no email invitation is sent.
      </p>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {manager && (
        <MutationForm
          label="Rename organization"
          action={async (data) => {
            await api.updateOrganization(org, String(data.get("name")));
            refresh();
          }}
        >
          <Field
            label="Organization display name"
            name="name"
            defaultValue={tenant.organization.name}
            required
            maxLength={160}
          />
        </MutationForm>
      )}
      {manager && (
        <MutationForm
          label="Add organization member"
          action={async (data) => {
            await api.addMember(
              org,
              String(data.get("username")),
              data.get("role") === "admin" ? "admin" : "member",
            );
            refresh();
          }}
        >
          <Field
            label="Registered username"
            name="username"
            required
            maxLength={150}
          />
          <label htmlFor="initial-member-role">Initial role</label>
          <select id="initial-member-role" name="role" defaultValue="member">
            <option value="member">Member</option>
            {owner && <option value="admin">Administrator</option>}
          </select>
        </MutationForm>
      )}
      <h2>Members</h2>
      <RetentionSettings org={org} owner={owner} />
      {!members ? (
        <p role="status">Loading members…</p>
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <caption>Current organization access</caption>
              <thead>
                <tr>
                  <th scope="col">Username</th>
                  <th scope="col">Role</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.results.map((member) => (
                  <tr key={member.id}>
                    <td>{member.user.username}</td>
                    <td>{member.role}</td>
                    <td>
                      {owner && member.role !== "owner" && (
                        <MutationForm
                          label={`Save role for ${member.user.username}`}
                          action={async (data) => {
                            await api.changeRole(
                              org,
                              member.id,
                              data.get("role") === "admin" ? "admin" : "member",
                            );
                            refresh();
                          }}
                        >
                          <label htmlFor={`member-role-${member.id}`}>
                            Role for {member.user.username}
                          </label>
                          <select
                            id={`member-role-${member.id}`}
                            name="role"
                            defaultValue={member.role}
                          >
                            <option value="member">Member</option>
                            <option value="admin">Administrator</option>
                          </select>
                        </MutationForm>
                      )}
                      {manager &&
                        member.role !== "owner" &&
                        (owner || member.role === "member") && (
                          <MutationForm
                            label={`Remove ${member.user.username}`}
                            action={async () => {
                              await api.removeMember(org, member.id);
                              refresh();
                            }}
                          >
                            <p>
                              Revoke organization access for{" "}
                              {member.user.username}.
                            </p>
                          </MutationForm>
                        )}
                      {owner && member.role !== "owner" && (
                        <MutationForm
                          label={`Transfer ownership to ${member.user.username}`}
                          action={async (data) => {
                            if (
                              String(data.get("confirm")) !==
                              member.user.username
                            )
                              throw new ApiError(
                                400,
                                "Enter the new owner’s username exactly.",
                              );
                            await api.transferOwnership(org, member.id);
                            refresh();
                          }}
                        >
                          <p>
                            This member becomes the sole owner. You become an
                            administrator. Enter their username to confirm.
                          </p>
                          <Field
                            label={`Confirm new owner ${member.user.username}`}
                            name="confirm"
                            required
                            maxLength={150}
                          />
                        </MutationForm>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            count={members.count}
            hasNext={members.next !== null}
            change={(value) => {
              setMembers(null);
              setPage(value);
            }}
          />
        </>
      )}
      {manager && (
        <>
          <h2>Audit history</h2>
          {!events ? (
            <p role="status">Loading audit history…</p>
          ) : (
            <>
              <div className="table-scroll">
                <table>
                  <caption>Recorded organization changes</caption>
                  <thead>
                    <tr>
                      <th scope="col">Time</th>
                      <th scope="col">Action</th>
                      <th scope="col">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.results.map((event) => (
                      <tr key={event.id}>
                        <td>{new Date(event.timestamp).toISOString()}</td>
                        <td>{event.action}</td>
                        <td>{event.outcome}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={auditPage}
                count={events.count}
                hasNext={events.next !== null}
                change={(value) => {
                  setEvents(null);
                  setAuditPage(value);
                }}
              />
            </>
          )}
        </>
      )}
      {owner && (
        <MutationForm
          label="Suspend organization"
          action={async (data) => {
            if (String(data.get("confirm")) !== tenant.organization.slug)
              throw new ApiError(400, "Enter the organization slug exactly.");
            await api.setOrganizationActive(org, false);
            refresh();
          }}
        >
          <p>
            Suspension denies protected access for every member. Enter the
            organization slug to confirm.
          </p>
          <Field
            label="Confirm suspension slug"
            name="confirm"
            required
            pattern={tenant.organization.slug}
          />
        </MutationForm>
      )}
    </>
  );
}

export default function OrganizationSettings({ org }: { org: string }) {
  const [generation, setGeneration] = useState(0);
  return (
    <TenantFrame
      key={`${org}:${generation}`}
      org={org}
      allowInactiveOrganization
    >
      <Settings
        refresh={() => {
          setGeneration((value) => value + 1);
          window.dispatchEvent(new Event("ppi:access-refresh"));
        }}
      />
    </TenantFrame>
  );
}
