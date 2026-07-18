import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const VALID_ROLES = ["admin", "manager", "member", "supplier"];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function generateTempPassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const segment = () =>
    Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  return `${segment()}-${segment()}-${segment()}`;
}

async function sendWelcomeEmail(
  to: string,
  fullName: string,
  tempPassword: string,
  resendApiKey: string,
): Promise<void> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${resendApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "ECTOFORM <noreply@ectoform.studio>",
      to: [to],
      subject: "You've been invited to ECTOFORM",
      html: `
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#1a1d22;color:#e0ecf4;border-radius:8px;">
          <h2 style="color:#5294e2;margin-top:0;">Welcome to ECTOFORM</h2>
          <p>Hi ${fullName},</p>
          <p>You've been added to your team's ECTOFORM workspace. Use the credentials below to sign in.</p>
          <div style="background:#22262c;border-radius:6px;padding:16px 24px;margin:24px 0;">
            <p style="margin:0 0 8px;color:#8b9cb3;font-size:13px;">EMAIL</p>
            <p style="margin:0 0 16px;font-size:15px;">${to}</p>
            <p style="margin:0 0 8px;color:#8b9cb3;font-size:13px;">TEMPORARY PASSWORD</p>
            <p style="margin:0;font-size:20px;font-weight:bold;letter-spacing:2px;color:#5294e2;">${tempPassword}</p>
          </div>
          <p style="color:#8b9cb3;font-size:13px;">Open the ECTOFORM desktop app and sign in with the credentials above. You can change your password after logging in.</p>
        </div>
      `,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend error ${res.status}: ${body}`);
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) return json({ error: "Missing authorization header" }, 401);

    const body = await req.json().catch(() => null);
    if (!body) return json({ error: "Invalid JSON body" }, 400);

    const { email, full_name, role } = body as {
      email?: string;
      full_name?: string;
      role?: string;
    };

    if (!email || !full_name || !role) {
      return json({ error: "email, full_name and role are required" }, 400);
    }
    if (!VALID_ROLES.includes(role)) {
      return json({ error: `Invalid role. Must be one of: ${VALID_ROLES.join(", ")}` }, 400);
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const resendApiKey = Deno.env.get("RESEND_API_KEY") ?? "";

    // Verify caller identity using their JWT
    const callerClient = createClient(supabaseUrl, anonKey, {
      global: { headers: { Authorization: authHeader } },
    });

    const { data: { user: caller }, error: authErr } = await callerClient.auth.getUser();
    if (authErr || !caller) return json({ error: "Invalid or expired session" }, 401);

    // Confirm caller is an admin
    const { data: callerProfile, error: profileErr } = await callerClient
      .from("profiles")
      .select("role, company_id")
      .eq("id", caller.id)
      .single();

    if (profileErr || !callerProfile) return json({ error: "Could not verify caller profile" }, 403);
    if (callerProfile.role !== "admin") return json({ error: "Only admins can invite users" }, 403);

    const companyId: string = callerProfile.company_id;

    // Admin client for privileged operations
    const adminClient = createClient(supabaseUrl, serviceKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });

    const tempPassword = generateTempPassword();

    // Create auth user with confirmed email — no magic link
    const { data: newUserData, error: createErr } = await adminClient.auth.admin.createUser({
      email,
      password: tempPassword,
      email_confirm: true,
    });

    if (createErr) {
      const msg = createErr.message ?? "";
      if (
        msg.includes("already been registered") ||
        msg.includes("already registered") ||
        msg.includes("User already registered")
      ) {
        return json({ error: "A user with this email already exists." }, 409);
      }
      throw createErr;
    }

    const newUserId = newUserData.user.id;

    // Insert profile
    const { error: insertErr } = await adminClient.from("profiles").insert({
      id: newUserId,
      full_name,
      role,
      company_id: companyId,
    });

    if (insertErr) {
      await adminClient.auth.admin.deleteUser(newUserId);
      throw insertErr;
    }

    // Send welcome email with temp password
    if (resendApiKey) {
      await sendWelcomeEmail(email, full_name, tempPassword, resendApiKey);
    }

    return json({
      success: true,
      user_id: newUserId,
      temp_password: tempPassword,
      email_sent: !!resendApiKey,
    });

  } catch (err) {
    console.error("invite-user error:", err);
    return json({ error: (err as Error).message ?? "Internal server error" }, 500);
  }
});
