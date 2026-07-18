import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
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

    const { user_id } = body as { user_id?: string };
    if (!user_id) return json({ error: "user_id is required" }, 400);

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

    // Verify caller identity
    const callerClient = createClient(supabaseUrl, anonKey, {
      global: { headers: { Authorization: authHeader } },
    });

    const { data: { user: caller }, error: authErr } = await callerClient.auth.getUser();
    if (authErr || !caller) return json({ error: "Invalid or expired session" }, 401);

    // Confirm caller is admin
    const { data: callerProfile, error: profileErr } = await callerClient
      .from("profiles")
      .select("role, company_id")
      .eq("id", caller.id)
      .single();

    if (profileErr || !callerProfile) return json({ error: "Could not verify caller profile" }, 403);
    if (callerProfile.role !== "admin") return json({ error: "Only admins can remove users" }, 403);

    // Prevent self-removal
    if (user_id === caller.id) return json({ error: "You cannot remove your own account." }, 400);

    // Admin client for privileged operations
    const adminClient = createClient(supabaseUrl, serviceKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });

    // Confirm target user is in the same company
    const { data: targetProfile, error: targetErr } = await adminClient
      .from("profiles")
      .select("company_id, role")
      .eq("id", user_id)
      .single();

    if (targetErr || !targetProfile) return json({ error: "User not found" }, 404);
    if (targetProfile.company_id !== callerProfile.company_id) {
      return json({ error: "User is not in your company" }, 403);
    }

    // Delete profile first, then auth user
    await adminClient.from("profiles").delete().eq("id", user_id);
    const { error: deleteErr } = await adminClient.auth.admin.deleteUser(user_id);
    if (deleteErr) throw deleteErr;

    return json({ success: true, message: "User removed successfully" });

  } catch (err) {
    console.error("remove-user error:", err);
    return json({ error: (err as Error).message ?? "Internal server error" }, 500);
  }
});
