import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { SessionExpiredError } from "../../services/apiClient";
import * as profileService from "../../services/profileService";
import { lookupFrom } from "./useProfileFields";

// A failed county lookup must not hide the profile; the form can look up again.
function withCounties(profile) {
  if (!profile.zip_code) return { profile, counties: undefined };
  return profileService.lookupCounties(profile.zip_code).then(
    (data) => ({ profile, counties: lookupFrom(data) }),
    () => ({ profile, counties: undefined }),
  );
}

export function useProfile() {
  const { token, expireSession, updateUser } = useAuth();
  const [loaded, setLoaded] = useState({ profile: null, counties: undefined });
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  const fetchProfile = useCallback(() => {
    return profileService.getProfile(token).then(withCounties).then(
      (data) => {
        setLoaded(data);
        setStatus("ready");
      },
      (err) => {
        if (err instanceof SessionExpiredError) return expireSession();
        setError(err.message);
        setStatus("error");
      },
    );
  }, [token, expireSession]);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const retry = useCallback(() => {
    setStatus("loading");
    setError("");
    fetchProfile();
  }, [fetchProfile]);

  async function save(changes) {
    try {
      const saved = await profileService.updateProfile(token, changes);
      updateUser({ profile_complete: true });
      return saved;
    } catch (err) {
      if (err instanceof SessionExpiredError) expireSession();
      throw err;
    }
  }

  return { profile: loaded.profile, counties: loaded.counties, status, error, retry, save };
}
